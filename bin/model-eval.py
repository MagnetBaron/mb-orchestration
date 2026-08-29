#!/usr/bin/env python3
"""model-eval — validate and score normalized JSONL evaluation receipts.

Correctness and token efficiency dominate. Latency is recorded and has weight 0
(or a negligible default of 0). A receipt never grants tools, credentials, or
routing authority.

Receipt JSONL (one object per line, secret-free):

  {
    "case_id": "brief-routing-1",
    "model": "claude-opus-5",
    "route": "opus-5-teamclaude",
    "output": "...",
    "tokens_in": 1200,
    "tokens_out": 400,
    "latency_ms": 8000,
    "correctness": 0.0-1.0,          # optional if gold matching is used
    "flags": ["invented_metric"]     # optional
  }

Gold answers live in model-evals/cases.json. When a case has `gold`, the scorer
computes correctness from required/forbidden substrings unless `correctness` is
supplied explicitly.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
DEFAULT_CASES = REPO / "model-evals" / "cases.json"
DEFAULT_WEIGHTS = {
    "correctness": 0.70,
    "token_efficiency": 0.25,
    "evidence_discipline": 0.05,
    "latency": 0.0,
}


class EvalError(ValueError):
    pass


def load_cases(path: Path | None = None) -> dict:
    p = path or DEFAULT_CASES
    try:
        data = json.loads(p.read_text())
    except Exception as exc:
        raise EvalError(f"cannot parse cases {p}: {exc}") from exc
    if data.get("schema_version") != 1:
        raise EvalError("cases.json must use schema_version 1")
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        raise EvalError("cases.json must contain a non-empty cases list")
    ids = [c.get("id") for c in cases]
    if len(ids) != len(set(ids)):
        raise EvalError("cases.json ids must be unique")
    required_suites = {
        "routing_brief_quality",
        "context_compression_recall",
        "defect_review",
        "implementation_planning",
        "evidence_discipline",
        "token_efficiency",
    }
    suites = {c.get("suite") for c in cases}
    missing = required_suites - suites
    if missing:
        raise EvalError(f"cases.json missing required suites: {sorted(missing)}")
    return data


def validate_cases(data: dict) -> list[str]:
    errors = []
    for i, case in enumerate(data.get("cases") or []):
        if not isinstance(case, dict):
            errors.append(f"cases[{i}]: must be an object")
            continue
        for field in ("id", "suite", "role", "prompt"):
            if not case.get(field):
                errors.append(f"cases[{i}]: missing {field}")
        gold = case.get("gold")
        if gold is not None and not isinstance(gold, dict):
            errors.append(f"cases[{i}]: gold must be an object")
        if case.get("secret") or "sk-" in json.dumps(case):
            errors.append(f"cases[{i}]: appears to contain a secret — fixtures must be secret-free")
    weights = data.get("weights") or DEFAULT_WEIGHTS
    lat = float(weights.get("latency", 0) or 0)
    if lat > 0.05:
        errors.append(f"latency weight {lat} is too high; latency must be 0 or negligible (<=0.05)")
    return errors


def token_efficiency(tokens_out, budget) -> float:
    if not budget or budget <= 0:
        return 1.0
    if tokens_out is None:
        return 0.0
    # 1.0 at or under budget; decays as output grows. Never negative.
    ratio = max(0.0, float(tokens_out)) / float(budget)
    return max(0.0, min(1.0, 1.0 / (1.0 + max(0.0, ratio - 1.0))))


def gold_correctness(output: str, gold: dict) -> float:
    text = output or ""
    lowered = text.lower()
    required = gold.get("must_contain") or []
    forbidden = gold.get("must_not_contain") or []
    hits = 0
    total = 0
    for needle in required:
        total += 1
        if str(needle).lower() in lowered:
            hits += 1
    for needle in forbidden:
        total += 1
        if str(needle).lower() not in lowered:
            hits += 1
    any_of = gold.get("must_contain_any") or []
    if any_of:
        total += 1
        if any(str(n).lower() in lowered for n in any_of):
            hits += 1
    if total == 0:
        return 0.0
    return hits / total


def evidence_score(receipt: dict, case: dict) -> float:
    """Penalize invented metrics / missing citations when the case requires evidence discipline."""
    flags = set(receipt.get("flags") or [])
    gold = case.get("gold") or {}
    banned_flags = set(gold.get("banned_flags") or ["invented_metric", "no_citation"])
    if case.get("suite") != "evidence_discipline" and not gold.get("banned_flags"):
        return 1.0
    if flags & banned_flags:
        return 0.0
    output = (receipt.get("output") or "").lower()
    required_markers = gold.get("evidence_markers") or []
    if required_markers and not any(m.lower() in output for m in required_markers):
        return 0.0
    return 1.0


def score_receipt(receipt: dict, case: dict, weights: dict | None = None) -> dict:
    if not isinstance(receipt, dict):
        raise EvalError("receipt must be an object")
    if receipt.get("case_id") != case.get("id"):
        raise EvalError(f"receipt case_id {receipt.get('case_id')!r} != case {case.get('id')!r}")
    w = dict(DEFAULT_WEIGHTS)
    w.update(weights or {})
    if float(w.get("latency") or 0) > 0.05:
        raise EvalError("latency weight must be 0 or negligible")
    output = receipt.get("output") or ""
    if "correctness" in receipt:
        correctness = float(receipt["correctness"])
    elif case.get("gold"):
        correctness = gold_correctness(output, case["gold"])
    else:
        raise EvalError(f"receipt for {case['id']} needs correctness or the case needs gold")
    if not 0.0 <= correctness <= 1.0:
        raise EvalError("correctness must be in [0, 1]")
    budget = (case.get("token_budget_out")
              or (case.get("gold") or {}).get("token_budget_out")
              or 400)
    efficiency = token_efficiency(receipt.get("tokens_out"), budget)
    evidence = evidence_score(receipt, case)
    latency_ms = receipt.get("latency_ms")
    total = (
        w["correctness"] * correctness
        + w["token_efficiency"] * efficiency
        + w["evidence_discipline"] * evidence
        + float(w.get("latency") or 0) * 0.0
    )
    return {
        "case_id": case["id"],
        "suite": case.get("suite"),
        "role": case.get("role"),
        "model": receipt.get("model"),
        "route": receipt.get("route"),
        "correctness": round(correctness, 4),
        "token_efficiency": round(efficiency, 4),
        "evidence_discipline": round(evidence, 4),
        "latency_ms": latency_ms,
        "latency_weight": float(w.get("latency") or 0),
        "tokens_in": receipt.get("tokens_in"),
        "tokens_out": receipt.get("tokens_out"),
        "total": round(total, 4),
        "authority_grants": False,
    }


def read_jsonl(path: Path) -> list[dict]:
    rows = []
    for i, line in enumerate(path.read_text().splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except Exception as exc:
            raise EvalError(f"{path}:{i}: invalid JSON: {exc}") from exc
        if not isinstance(obj, dict):
            raise EvalError(f"{path}:{i}: receipt must be an object")
        if "sk-" in line or obj.get("api_key") or obj.get("secret"):
            raise EvalError(f"{path}:{i}: receipt appears to contain a secret")
        rows.append(obj)
    return rows


def score_file(receipts_path: Path, cases: dict) -> dict:
    by_id = {c["id"]: c for c in cases["cases"]}
    weights = cases.get("weights") or DEFAULT_WEIGHTS
    receipts = read_jsonl(receipts_path)
    if not receipts:
        raise EvalError("no receipts")
    scored = []
    for rec in receipts:
        cid = rec.get("case_id")
        if cid not in by_id:
            raise EvalError(f"unknown case_id {cid!r}")
        scored.append(score_receipt(rec, by_id[cid], weights))
    totals = [s["total"] for s in scored]
    return {
        "n": len(scored),
        "mean_total": round(sum(totals) / len(totals), 4),
        "mean_correctness": round(sum(s["correctness"] for s in scored) / len(scored), 4),
        "mean_token_efficiency": round(sum(s["token_efficiency"] for s in scored) / len(scored), 4),
        "mean_latency_ms": (
            round(sum(s["latency_ms"] for s in scored if s["latency_ms"] is not None)
                  / max(1, sum(1 for s in scored if s["latency_ms"] is not None)), 1)
            if any(s["latency_ms"] is not None for s in scored) else None
        ),
        "latency_weight": float(weights.get("latency") or 0),
        "authority_grants": False,
        "results": scored,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Score normalized model-eval JSONL receipts.")
    ap.add_argument("receipts", nargs="?", type=Path, help="JSONL receipts path")
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--validate-cases", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)

    cases = load_cases(args.cases)
    errors = validate_cases(cases)
    if errors:
        print("cases INVALID", file=sys.stderr)
        for e in errors:
            print(f"  ✗ {e}", file=sys.stderr)
        return 1
    if args.validate_cases and not args.receipts:
        print(f"cases OK ({len(cases['cases'])} cases)")
        return 0
    if not args.receipts:
        print("model-eval: pass a JSONL receipts file, or --validate-cases", file=sys.stderr)
        return 2
    blob = score_file(args.receipts, cases)
    if args.json:
        print(json.dumps(blob, indent=2))
    else:
        print(f"n={blob['n']} mean_total={blob['mean_total']} "
              f"correctness={blob['mean_correctness']} "
              f"token_efficiency={blob['mean_token_efficiency']} "
              f"latency_ms={blob['mean_latency_ms']} (weight {blob['latency_weight']})")
        for s in blob["results"]:
            print(f"  {s['case_id']}: total={s['total']} corr={s['correctness']} "
                  f"tok={s['token_efficiency']} lat={s['latency_ms']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

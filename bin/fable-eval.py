#!/usr/bin/env python3
"""fable-eval — administer the 3 clean-room Fable placement trials and blind-grade them.

WHAT THIS IS (and is not)
-------------------------
A human-facing MEASUREMENT tool, in the spirit of USER-GUIDE.md: it produces the
*data* behind an owner decision, it does not make the call and it is never loaded
into an agent's operating context. It runs the three trials in
`fable-tests.md` (coding-logic / brand-voice / architecture-critique), each a cold,
no-memory, blind A/B between two arms, and prints a scoresheet plus a recommended
`providers.json` prowess/home edit per axis.

Fable is being measured for a **GENERATION home only.** By owner ruling (2026-08-25,
Orchestration Retro) Fable is already OUT of the gating/refusal order and out of
dispatch — it measured worst on nonsense detection (BullshitBench). These trials say
nothing about that and cannot put it back into gating. They only ask: does Fable
*generate* well enough on some axis to earn a NON-gating seat? A seat is earned on an
axis only where Fable **clearly beats** Opus 4.8 (mean gap >= 1.5 / 10 AND a majority
of paired runs). A tie or a loss = no seat.

HOW IT RUNS THE MODELS — teamclaude
-----------------------------------
Both arms and the voice grader are Claude models reached through **teamclaude**, which
owns Claude-seat routing (rotating the 5 seats across 5h windows, tracking per-model
caps). The single invocation lives in ONE place: `run_via_teamclaude()` below. It is
the only spot that shells out; edit the command/flags/model-ids THERE. teamclaude is
installed on the Mini, not in every environment, so without it use `--dry-run`, which
swaps deterministic stub outputs in for the model calls and exercises the entire
parse -> administer -> grade -> score -> verdict pipeline end to end.

GRADING
-------
  * coding + architecture  -> objective, deterministic checks IN CODE against a
    structured answer key (did it catch each planted defect? did it false-flag the
    labelled non-defect / distractor?). Same text -> same score.
  * content / brand voice  -> a blind model grader (a NON-Fable model via teamclaude)
    scores 0-10 against the rubric+answer_key; it never learns which arm wrote the
    text. Objective mechanical facts (word count, banned words, required facts, CTA)
    are computed in code and handed to the grader so only fabrication + voice need
    judgement.

Every raw output is saved under `mborch.data_dir()/fable-eval/` (gitignored) so the
owner can re-grade by hand. The A/B label map is recorded separately from the graded
text so the blind stays a blind.

USAGE
  bin/fable-eval.py --dry-run                 # prove the pipeline with stub outputs
  bin/fable-eval.py --tests <path> --k 3      # real run on the teamclaude Mini
  bin/fable-eval.py --dry-run --json          # machine-readable
  bin/fable-eval.py --build-sidecar           # extract md -> fable-tests.json (+ prompts-only)

The recommended providers.json edits are PRINTED ONLY. This tool never writes config;
applying the edit is a separate, reviewed land step (another lane owns providers.json).
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import shutil
import string
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import mborch  # noqa: E402  (shared config/data resolution — used for data_dir())

# ======================================================================================
# THE teamclaude INVOCATION  --  the ONE editable spot for how models are called
# ======================================================================================
# teamclaude routes a prompt to a live Claude seat that can serve `model`. We use Claude
# Code *print mode* (`-p`): a single-shot, no-memory, no-prior-turns completion on stdout
# — exactly what a cold clean-room trial needs. Everything after `--` is passed straight
# through to the underlying `claude` CLI.
#
#   OWNER: confirm/edit the exact binary, subcommand, passthrough marker, flags, and the
#   model ids for YOUR Mini before the first real (non --dry-run) run. The model ids
#   default to whatever providers.json lists for fable-5 / opus-4.8 (see resolve_models),
#   so they never go stale in prose; override per-run with --fable-model / --opus-model /
#   --grader-model, or set them permanently in providers.json.
#
# Default command template (edit here if your teamclaude differs):
#       teamclaude run -- -p "<prompt>" --model <model-id>
# Common tweaks: add `--output-format text`, `--max-turns 1`, or a per-seat `--profile`.
TEAMCLAUDE_BIN = os.environ.get("TEAMCLAUDE_BIN", "teamclaude")
TEAMCLAUDE_ARGV = os.environ.get("TEAMCLAUDE_ARGV", "run,--,-p,{prompt},--model,{model}")
DEFAULT_TIMEOUT = int(os.environ.get("FABLE_EVAL_TIMEOUT", "300"))


class TeamclaudeError(RuntimeError):
    pass


def teamclaude_available() -> bool:
    """True if the teamclaude binary is on PATH (real runs need it; --dry-run does not)."""
    return shutil.which(TEAMCLAUDE_BIN) is not None


def run_via_teamclaude(model: str, prompt: str, *, timeout: int = DEFAULT_TIMEOUT) -> str:
    """Run ONE cold, single-shot completion of `prompt` on `model`, via teamclaude.

    This is the sole place the tool talks to a model. Both trial arms (fable, opus) and
    the blind voice grader come through here. The taker/grader sees ONLY the string in
    `prompt` — no rubric, no answer key, no arm identity, no test metadata.

    Returns the model's stdout (stripped). Raises TeamclaudeError on any non-zero exit or
    launch failure so the caller fails closed rather than grading an empty answer.
    """
    argv = [part.format(prompt=prompt, model=model) for part in TEAMCLAUDE_ARGV.split(",")]
    cmd = [TEAMCLAUDE_BIN, *argv]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError as exc:
        raise TeamclaudeError(f"teamclaude binary {TEAMCLAUDE_BIN!r} not found on PATH") from exc
    except subprocess.TimeoutExpired as exc:
        raise TeamclaudeError(f"teamclaude timed out after {timeout}s for model {model}") from exc
    if proc.returncode != 0:
        raise TeamclaudeError(
            f"teamclaude exit {proc.returncode} for model {model}: {proc.stderr.strip()[:400]}"
        )
    return proc.stdout.strip()


# ======================================================================================
# Model-id resolution — single source of truth is providers.json (no stale ids in code)
# ======================================================================================
FALLBACK_MODELS = {"fable": "claude-fable-5", "opus": "claude-opus-4-8"}


def _safe_providers() -> dict:
    """Load providers.json, degrading to {} on any error (a concurrent config edit must
    not crash a measurement run — model ids fall back to FALLBACK_MODELS)."""
    try:
        return mborch.load_config("providers.json", required=False) or {}
    except SystemExit:
        print("fable-eval: WARNING — providers.json unreadable right now; using fallback model ids.",
              file=sys.stderr)
        return {}


def resolve_models(args) -> dict:
    """fable / opus / grader model ids, from providers.json unless overridden on the CLI.

    Grader defaults to the Opus id (a NON-Fable frontier reachable via teamclaude) and is
    refused if it equals the Fable id — a blind grader must not be an arm under test.
    """
    prov = _safe_providers().get("providers", {})
    fable = args.fable_model or prov.get("fable-5", {}).get("model") or FALLBACK_MODELS["fable"]
    opus = args.opus_model or prov.get("opus-4.8", {}).get("model") or FALLBACK_MODELS["opus"]
    grader = args.grader_model or opus
    if grader == fable:
        raise SystemExit(
            "fable-eval: grader model must be a NON-Fable model (blind grader cannot be an arm). "
            "Pass --grader-model with a different id."
        )
    return {"fable": fable, "opus": opus, "grader": grader}


# ======================================================================================
# Loading the tests  (parse fable-tests.md; or read a sidecar json)
# ======================================================================================
FENCE4 = "````"  # exactly-four-backtick lines delimit each PROMPT (prompts contain ``` blocks)


def _canonical_id(axis: str, index: int) -> str:
    a = (axis or "").lower()
    if "coding" in a or "completeness" in a:
        return "coding"
    if "content" in a or "voice" in a or "brand" in a:
        return "content"
    if "architecture" in a or "design" in a:
        return "architecture"
    return f"test{index + 1}"


def parse_markdown(md_path: Path) -> list[dict]:
    """Split fable-tests.md into [{id, axis, prompt, rubric, answer_key}], prompt verbatim.

    Robust because the source uses unambiguous delimiters: `## Test N` starts a section,
    a line of exactly four backticks opens/closes the PROMPT, and `**Rubric`/`**Answer
    key:**` bound the grader-only material. The PROMPT text is taken verbatim between the
    first pair of four-backtick fences (it may itself contain ``` code blocks).
    """
    lines = md_path.read_text().splitlines()
    # section starts: every "## Test ..." header; a section runs to the next "## " header
    heads = [i for i, ln in enumerate(lines) if ln.startswith("## Test")]
    if not heads:
        raise SystemExit(f"fable-eval: no '## Test' sections found in {md_path}")
    bounds = []
    for k, start in enumerate(heads):
        end = len(lines)
        for j in range(start + 1, len(lines)):
            if lines[j].startswith("## "):
                end = j
                break
        bounds.append((start, end))

    tests = []
    for idx, (start, end) in enumerate(bounds):
        seg = lines[start:end]
        axis = _extract_axis(seg)
        prompt = _extract_prompt(seg, md_path, start)
        rubric = _extract_block(seg, "**Rubric", ("**Answer key", "## "))
        answer_key = _extract_block(seg, "**Answer key", ("## ", "---SENTINEL---"))
        tid = _canonical_id(axis, idx)
        tests.append({"id": tid, "axis": axis or tid, "prompt": prompt,
                      "rubric": rubric.strip(), "answer_key": answer_key.strip()})
    return tests


def _extract_axis(seg: list[str]) -> str:
    """Pull the `axis` field out of the ```json ... ``` block in a section."""
    inside, buf = False, []
    for ln in seg:
        if ln.strip().startswith("```json"):
            inside = True
            continue
        if inside and ln.strip() == "```":
            break
        if inside:
            buf.append(ln)
    if not buf:
        return ""
    try:
        return json.loads("\n".join(buf)).get("axis", "")
    except Exception:
        m = re.search(r'"axis"\s*:\s*"([^"]+)"', "\n".join(buf))
        return m.group(1) if m else ""


def _extract_prompt(seg: list[str], md_path: Path, start: int) -> str:
    """Verbatim text strictly between the first pair of exactly-four-backtick fences."""
    fence_rel = [i for i, ln in enumerate(seg) if ln.rstrip() == FENCE4]
    if len(fence_rel) < 2:
        raise SystemExit(
            f"fable-eval: could not find a four-backtick PROMPT fence pair in the section "
            f"starting at {md_path}:{start + 1}"
        )
    a, b = fence_rel[0], fence_rel[1]
    return "\n".join(seg[a + 1:b])


def _extract_block(seg: list[str], start_marker: str, stop_prefixes) -> str:
    """Text from a `**Marker...` line up to the next stop prefix (exclusive of both)."""
    out, capturing = [], False
    for ln in seg:
        if not capturing and ln.startswith(start_marker):
            capturing = True
            continue
        if capturing and any(ln.startswith(p) for p in stop_prefixes):
            break
        if capturing:
            out.append(ln)
    return "\n".join(out)


def load_tests(path: Path) -> list[dict]:
    """Load trials from a .json sidecar or a .md source, by extension."""
    if path.suffix == ".json":
        data = json.loads(path.read_text())
        tests = data["tests"] if isinstance(data, dict) and "tests" in data else data
        for t in tests:
            for f in ("id", "prompt"):
                if f not in t:
                    raise SystemExit(f"fable-eval: sidecar test missing {f!r}: {t.get('id', '?')}")
        return tests
    return parse_markdown(path)


def resolve_tests_path(cli: str | None) -> Path:
    """Find the trials file: --tests, then $MB_FABLE_TESTS, then known data/CWD locations."""
    cands: list[Path] = []
    if cli:
        cands.append(Path(cli).expanduser())
    env = os.environ.get("MB_FABLE_TESTS")
    if env:
        cands.append(Path(env).expanduser())
    for base in (mborch.data_dir() / "fable-eval", mborch.REPO / "data" / "fable-eval", Path.cwd()):
        cands += [base / "fable-tests.json", base / "fable-tests.md"]
    for c in cands:
        if c.exists():
            return c
    raise SystemExit(
        "fable-eval: no trials file found. Pass --tests <path to fable-tests.md|.json>, "
        "or set $MB_FABLE_TESTS. (Looked in: "
        + ", ".join(str(c) for c in cands) + ")"
    )


def taker_view(test: dict) -> dict:
    """The ONLY fields a taker ever sees. Enforces prompt/answer separation in code."""
    return {"id": test["id"], "prompt": test["prompt"]}


def build_sidecar(md_path: Path, out_path: Path, prompts_only: bool) -> list[Path]:
    """Extract md -> combined sidecar json; optionally also a taker-safe prompts-only file."""
    tests = parse_markdown(md_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"source": str(md_path), "tests": tests}, indent=2) + "\n")
    written = [out_path]
    if prompts_only:
        p = out_path.with_name(out_path.stem.replace("tests", "prompts") + out_path.suffix)
        if p == out_path:
            p = out_path.with_name("fable-prompts.json")
        p.write_text(json.dumps({"tests": [taker_view(t) for t in tests]}, indent=2) + "\n")
        written.append(p)
    return written


# ======================================================================================
# Deterministic detector helpers
# ======================================================================================
def _compile(patterns) -> list:
    return [re.compile(p, re.I) for p in patterns]


def near(text: str, loc_patterns, cue_patterns, window: int = 300) -> bool:
    """True if any cue pattern appears within `window` chars of any location pattern."""
    locs = _compile(loc_patterns)
    cues = _compile(cue_patterns)
    for lc in locs:
        for m in lc.finditer(text):
            lo = max(0, m.start() - window)
            hi = min(len(text), m.end() + window)
            chunk = text[lo:hi]
            if any(c.search(chunk) for c in cues):
                return True
    return False


def _any(text: str, patterns) -> bool:
    return any(re.search(p, text, re.I) for p in patterns)


POS_VERDICT = [r"\bcorrect\b", r"\bok\b", r"\bfine\b", r"\bright\b", r"\bvalid\b", r"✓",
               r"\bgood\b", r"\bconsistent\b", r"no issue", r"no problem", r"\baccurate\b"]
NEG_VERDICT = [r"\bincorrect\b", r"\bwrong\b", r"\bbug\b", r"\bdefect\b", r"✗", r"\berror\b",
               r"\bissue\b", r"\bproblem\b", r"should be", r"\bbroken\b", r"\bmistake\b", r"\bmissed\b"]


def verdict_for_site(text: str, site: int, sites, fwd: int = 160) -> str | None:
    """Polarity ('pos'/'neg'/None) of the verdict the answer gives for one call-site.

    The scan is scoped FORWARD from each mention of the site number and truncated at the
    next call-site token or a blank line, so a dense enumeration ("- line 39 ... correct.
    / - line 43 ... incorrect.") cannot bleed one line's verdict onto its neighbour — the
    adjacency bug that a symmetric char-window silently produces. Occurrences that
    disagree resolve to None (ambiguous -> no credit).
    """
    loc = re.compile(rf"\b{site}\b")
    others = [s for s in sites if s != site]
    bnd = re.compile(r"\b(" + "|".join(str(s) for s in others) + r")\b") if others else None
    pos_c, neg_c = _compile(POS_VERDICT), _compile(NEG_VERDICT)
    seen = set()
    for m in loc.finditer(text):
        end = m.end() + fwd
        if bnd:
            nb = bnd.search(text, m.end())
            if nb:
                end = min(end, nb.start())
        nn = text.find("\n\n", m.end())
        if nn != -1:
            end = min(end, nn)
        chunk = text[m.start():end]
        has_neg = any(p.search(chunk) for p in neg_c)
        has_pos = any(p.search(chunk) for p in pos_c)
        if has_neg and not has_pos:
            seen.add("neg")
        elif has_pos and not has_neg:
            seen.add("pos")
    clean = {s for s in seen if s in ("pos", "neg")}
    if clean == {"pos"}:
        return "pos"
    if clean == {"neg"}:
        return "neg"
    return None  # absent or conflicting -> no credit (conservative)


def scoped_lines(text: str, anchor_patterns, avoid_patterns=None, include_next: bool = True) -> str:
    """Join the lines that match an anchor (plus each one's continuation line), for a
    LINE-scoped cue check. The continuation line is skipped if it matches `avoid_patterns`
    (e.g. an enumeration line carrying its own verdict words), so a neighbouring call-site
    verdict cannot leak into, say, the line-18 false-positive check."""
    lines = text.splitlines()
    apat = _compile(anchor_patterns)
    avoid = _compile(avoid_patterns or [])
    idxs = [i for i, ln in enumerate(lines) if any(p.search(ln) for p in apat)]
    chosen = set(idxs)
    if include_next:
        for i in idxs:
            j = i + 1
            if j < len(lines) and not any(p.search(lines[j]) for p in avoid):
                chosen.add(j)
    return " ".join(lines[i] for i in sorted(chosen))


# ======================================================================================
# Grader: Test 1 — coding-logic / completeness  (deterministic, /10)
# ======================================================================================
def grade_coding(text: str) -> dict:
    t = text
    br = []

    fix43 = near(t, [r"\b43\b", r"checkout_vip"],
                 [r"\b500\b", r"\$5\.00", r"value_cents[^0-9]{0,8}500", r"= *500"], 320)
    fix56 = near(t, [r"\b56\b", r"\{total:\.2f\}", r"total:\s*\$", r"total:\.2f", r"format_receipt"],
                 [r"/\s*100", r"total\s*/\s*100", r"divide by 100", r"divided by 100"], 320)

    d1 = near(t, [r"\b43\b", r"checkout_vip"],
              [r"\b500\b", r"\$5\.00", r"5 cents", r"should be 500", r"\bmigrat", r"\bmissed\b",
               r"\bwrong\b", r"\bbug\b", r"\bdefect\b", r"\bincorrect\b"], 320)
    d2 = near(t, [r"\b56\b", r"\{total:\.2f\}", r"total:\s*\$", r"total:\.2f", r"format_receipt"],
              [r"/\s*100", r"\bdivide", r"100x", r"100 times", r"\bcents\b", r"\bmissing\b",
               r"\bwrong\b", r"\bbug\b", r"\bdefect\b", r"too large"], 320)

    expected = {35: "pos", 39: "pos", 43: "neg", 47: "pos"}
    sites = list(expected)
    enum_hits = {s: verdict_for_site(t, s, sites) for s in expected}
    enum_correct = sum(1 for s, exp in expected.items() if enum_hits[s] == exp)
    enum_pts = 0.5 * enum_correct

    fixes_pts = (0.5 if fix43 else 0.0) + (0.5 if fix56 else 0.0)

    # line-18 false-positive check: scope to the line-18 sentence so the enumeration's
    # "correct"/"incorrect" verdicts for OTHER lines cannot leak in.
    loc18 = [r"line\s*18\b", r"//\s*10000", r"\b10000\b", r"integer (floor|division)",
             r"percent branch"]
    site_tokens = [rf"\b{s}\b" for s in sites]
    scope18 = scoped_lines(t, loc18, avoid_patterns=site_tokens)
    bugcue = [r"\bbug\b", r"\bdefect\b", r"\berror\b", r"\bincorrect\b", r"\bwrong\b",
              r"\bproblem\b", r"loses", r"\blost\b", r"rounding (bug|error)", r"should be (round|fix)"]
    okcue = [r"by design", r"intentional", r"intended", r"not a bug", r"\bfine\b", r"acceptable",
             r"\bconsistent\b", r"\bcorrect\b", r"no fractional", r"expected", r"is fine"]
    fp18 = bool(scope18) and _any(scope18, bugcue) and not _any(scope18, okcue)
    precision_pts = 0.0 if fp18 else 1.0

    d1_pts, d2_pts = (3.0 if d1 else 0.0), (3.0 if d2 else 0.0)
    br.append(("D1 line 43 flat-coupon 5c (should be 500)", 3.0, d1_pts))
    br.append(("D2 line 56 ${total:.2f} missing /100", 3.0, d2_pts))
    br.append((f"Enumeration 35/39/43/47 verdicts ({enum_correct}/4 correct: {enum_hits})", 2.0, enum_pts))
    br.append((f"Correct fixes (43->500:{fix43}, 56->/100:{fix56})", 1.0, fixes_pts))
    br.append((f"Precision — line 18 //10000 not called a bug (false-positive={fp18})", 1.0, precision_pts))
    total = round(d1_pts + d2_pts + enum_pts + fixes_pts + precision_pts, 2)
    return {"score": total, "breakdown": [{"criterion": c, "max": m, "awarded": a} for c, m, a in br]}


# ======================================================================================
# Grader: Test 3 — architecture / design critique  (deterministic, /10)
# ======================================================================================
def grade_architecture(text: str) -> dict:
    t = text
    br = []

    flaw1 = _any(t, [r"idempoten", r"\bdedup"]) or near(
        t, [r"event[_ ]id", r"same event", r"redeliver", r"at-least-once", r"\bretr", r"replay"],
        [r"duplicate", r"\btwice\b", r"\bagain\b", r"\bdouble", r"multiple times", r"second time"], 300)
    flaw2 = _any(t, [r"lost[- ]update", r"read-modify-write", r"race condition"]) or near(
        t, [r"\brace\b", r"concurren", r"interleav", r"non-atomic", r"not atomic", r"simultaneous"],
        [r"balance", r"increment", r"\bupdate", r"credit", r"\blose\b", r"\blost\b", r"overwrite"], 300)
    flaw3 = near(
        t, [r"\bemail", r"synchronous", r"\bsync\b", r"6-8", r"6–8", r"step \(?d\)?", r"blocking"],
        [r"5\s*s\b", r"5[- ]second", r"\btimeout", r"\back\b", r"\bwindow\b", r"\bretr", r"resend",
         r"async", r"\bqueue", r"worker", r"background"], 340)

    fixA = _any(t, [r"on conflict"]) or near(
        t, [r"event[_ ]id", r"idempoten", r"\bdedup"],
        [r"unique", r"primary key", r"upsert", r"constraint", r"\binsert"], 260)
    fixB = _any(t, [r"balance\s*=\s*balance\s*\+", r"balance\s*\+=", r"for update"]) or near(
        t, [r"\batomic", r"single (statement|update)", r"optimistic", r"version column", r"compare-and-swap"],
        [r"balance", r"\bupdate", r"increment"], 240)
    fixC = near(
        t, [r"async", r"\bqueue", r"enqueue", r"worker", r"outbox", r"background", r"\bdefer"],
        [r"\bemail", r"receipt", r"\bsend", r"\b200\b", r"\back\b", r"response"], 300)
    fixes_pts = round((2.0 / 3.0) * sum([fixA, fixB, fixC]), 2)

    link1 = near(t, [r"6-8", r"6–8", r"synchronous", r"\bslow\b", r"blocking", r"\bemail"],
                 [r"5\s*s\b", r"5[- ]second", r"\bwindow\b", r"\btimeout", r"exceed", r"beyond", r"\bpast\b"], 300)
    link2 = near(t, [r"\bretr", r"resend", r"redeliver", r"at-least-once"],
                 [r"duplicate", r"\bagain\b", r"\btwice\b", r"idempoten", r"\bdouble", r"credit"], 300)
    auth_flag = near(t, [r"signature", r"authenticat", r"\bauth\b", r"\bverify\b"],
                     [r"missing", r"\bshould\b", r"\badd\b", r"not verif", r"vulnerab", r"insecure",
                      r"\bmust\b", r"\bfix\b", r"\bproblem\b"], 180)
    auth_ok = near(t, [r"signature", r"authenticat", r"\bauth\b", r"\bverify\b"],
                   [r"upstream", r"already verif", r"out of scope", r"handled upstream", r"as stated",
                    r"as given", r"middleware"], 180)
    false_claim = auth_flag and not auth_ok
    if false_claim:
        causal_pts = 0.0
    elif link1 and link2:
        causal_pts = 1.0
    elif link1 or link2:
        causal_pts = 0.5
    else:
        causal_pts = 0.0

    f1_pts, f2_pts, f3_pts = (3.0 if flaw1 else 0.0), (2.0 if flaw2 else 0.0), (2.0 if flaw3 else 0.0)
    br.append(("Flaw 1 — no idempotency/dedup (duplicate credit)", 3.0, f1_pts))
    br.append(("Flaw 2 — lost-update race (non-atomic read-modify-write)", 2.0, f2_pts))
    br.append(("Flaw 3 — sync email breaks the 5s ack window", 2.0, f3_pts))
    br.append((f"Correct fixes (dedup:{fixA}, atomic:{fixB}, async:{fixC})", 2.0, fixes_pts))
    br.append((f"Causal chain + no false claim (links {link1}/{link2}, auth-false-claim={false_claim})", 1.0, causal_pts))
    total = round(f1_pts + f2_pts + f3_pts + fixes_pts + causal_pts, 2)
    return {"score": total, "breakdown": [{"criterion": c, "max": m, "awarded": a} for c, m, a in br]}


# ======================================================================================
# Grader: Test 2 — content / brand voice  (mechanical in code + blind model grader)
# ======================================================================================
BANNED_WORDS = {
    "revolutionary": r"\brevolutionar\w*\b|\brevolutioniz\w*\b",
    "game-changer": r"\bgame[\s-]?chang\w*\b",
    "ultimate": r"\bultimate\w*\b",
    "amazing": r"\bamaz\w*\b",
    "effortless": r"\beffortless\w*\b",
    "premium": r"\bpremium\b",
    "cutting-edge": r"\bcutting[\s-]?edge\b",
}
PRONOUN_RE = re.compile(r"\b(we|our|us|i|my)\b", re.I)
EMOJI_RE = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF←-⇿⌀-⏿⬀-⯿]"
)
ALLOWED_CAPS = {"USB", "USB-C"}
CTA = "Set the light, get to work."
# Fabrication watch-list: any of these appearing = an invented spec (zeroes no-fabrication).
FABRICATION_RE = [
    r"\blumens?\b", r"\blux\b", r"\bmah\b", r"\$\s*\d", r"\bprice\b", r"\bdiscount\b",
    r"aircraft[- ]grade", r"anodiz", r"\bapp\b", r"voice control", r"\bsmart\b", r"dimming schedule",
    r"water[- ]?(resistant|proof)", r"dust[- ]?(resistant|proof)", r"\bip\d\d\b", r"flicker[- ]free",
    r"eye[- ]care", r"blue[- ]light", r"\bclamp\b", r"\bmount\b", r"\bstand\b", r"wireless charg",
]


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]


def _wc(s: str) -> int:
    return len(s.split())


def mechanical_content(text: str) -> dict:
    words = text.split()
    wc = len(words)
    length_ok = 50 <= wc <= 70
    sents = _sentences(text)
    over_sentences = [s for s in sents if _wc(s) > 15]

    tl = text.lower()
    f1 = bool(re.search(r"\b(four|4)\b", tl) and re.search(r"level", tl))
    f2 = "usb-c" in tl and bool(re.search(r"\b90\b", tl) and re.search(r"minute|min\b", tl))
    f3_has = bool(re.search(r"\b18\b", tl) and re.search(r"hour|hr\b", tl))
    f3_qualified = "lowest" in tl
    f3 = f3_has and f3_qualified
    f4 = bool(re.search(r"\b(1|one)[\s-]?year", tl) and re.search(r"warrant", tl))
    facts = {"four_levels": f1, "usbc_90min": f2, "18h_lowest": f3, "one_year_warranty": f4}
    facts_pts = 0.5 * sum(facts.values())

    banned_hits = sorted({w for w, pat in BANNED_WORDS.items() if re.search(pat, text, re.I)})
    pronoun_hits = sorted({m.group(0).lower() for m in PRONOUN_RE.finditer(text)})
    bang = "!" in text
    question = "?" in text
    emoji = bool(EMOJI_RE.search(text))
    allcaps_hits = []
    for tok in re.findall(r"\S+", text):
        core = tok.strip(string.punctuation)
        if len(core) >= 2 and core.isupper() and any(c.isalpha() for c in core) \
                and not any(c.isdigit() for c in core) and core not in ALLOWED_CAPS:
            allcaps_hits.append(core)
    allcaps_hits = sorted(set(allcaps_hits))
    cta_ok = text.rstrip().endswith(CTA)

    violations = []
    if over_sentences:
        violations.append(f"{len(over_sentences)} sentence(s) >15 words")
    if bang:
        violations.append("exclamation mark")
    if question:
        violations.append("question mark")
    if emoji:
        violations.append("emoji")
    for a in allcaps_hits:
        violations.append(f"all-caps '{a}'")
    for b in banned_hits:
        violations.append(f"banned word '{b}'")
    for p in pronoun_hits:
        violations.append(f"pronoun '{p}'")
    if not cta_ok:
        violations.append("missing/incorrect closing CTA")
    format_pts = max(0.0, 2.0 - 0.5 * len(violations))

    fab_hits = sorted({pat for pat in FABRICATION_RE if re.search(pat, text, re.I)})
    nofab_pts = 2.0 if not fab_hits else 0.0

    return {
        "word_count": wc, "length_ok": length_ok,
        "max_sentence_words": max((_wc(s) for s in sents), default=0),
        "facts": facts, "banned_hits": banned_hits, "pronoun_hits": pronoun_hits,
        "punctuation": {"exclamation": bang, "question": question, "emoji": emoji},
        "allcaps_hits": allcaps_hits, "cta_ok": cta_ok, "violations": violations,
        "fabrication_hits": fab_hits,
        "subscores": {
            "length": 1.0 if length_ok else 0.0,
            "facts": round(facts_pts, 2),
            "formatting": round(format_pts, 2),
            "no_fabrication": nofab_pts,
        },
    }


def build_grader_prompt(test: dict, candidate: str, mech: dict) -> str:
    """Blind voice-grader prompt: rubric + answer key + verified mechanical facts + text.

    The grader is NEVER told which arm produced the text. It uses the pre-verified
    mechanical facts for the mechanical lines and applies judgement only to fabrication
    and voice, returning a strict JSON object.
    """
    facts_line = json.dumps(mech["subscores"])
    return f"""You are a strict, impartial copy grader. Score the CANDIDATE copy below from 0 to 10
against the rubric and answer key. You do NOT know who wrote it; judge only the text.

RUBRIC
{test.get('rubric', '(rubric unavailable)')}

ANSWER KEY (grader-only; use to detect fabrication and check facts)
{test.get('answer_key', '(answer key unavailable)')}

PRE-VERIFIED MECHANICAL CHECKS (computed deterministically — trust these for the
length, facts, and formatting lines; do not recount):
{facts_line}
Full mechanical detail: {json.dumps({k: mech[k] for k in ('word_count','facts','violations','fabrication_hits')})}

Your job: (a) confirm no fabricated spec appears that is not on the fact sheet — any
invented item zeroes the no_fabrication line; (b) judge VOICE 0-3 (3 = natural, flowing,
varied openings, concrete; 2 = compliant but stiff; 1 = spec-list / awkward; 0 = off-voice
or padded).

Return ONLY a JSON object, no prose:
{{"length": <0-1>, "facts": <0-2>, "no_fabrication": <0-2>, "formatting": <0-2>,
  "voice": <0-3>, "total": <0-10>, "notes": "<one line>"}}

CANDIDATE
\"\"\"
{candidate}
\"\"\"
"""


def parse_grader_score(raw: str) -> dict:
    """Extract the grader's JSON verdict from raw model text; robust to fences/prose."""
    obj = None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    blob = m.group(1) if m else None
    if blob is None:
        m2 = re.search(r"\{.*\}", raw, re.S)
        blob = m2.group(0) if m2 else None
    if blob:
        try:
            obj = json.loads(blob)
        except Exception:
            obj = None
    if obj is None:
        m3 = re.search(r"total[\"']?\s*[:=]\s*([0-9]+(?:\.[0-9]+)?)", raw, re.I)
        if not m3:
            raise TeamclaudeError("grader returned no parseable JSON or total")
        return {"total": _clamp(float(m3.group(1)), 0, 10), "subscores": {}, "notes": "(salvaged total)"}
    subs = {k: obj.get(k) for k in ("length", "facts", "no_fabrication", "formatting", "voice")}
    if obj.get("total") is not None:
        total = float(obj["total"])
    else:
        total = sum(float(v) for v in subs.values() if isinstance(v, (int, float)))
    return {"total": round(_clamp(total, 0, 10), 2), "subscores": subs, "notes": obj.get("notes", "")}


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def grade_content(candidate: str, test: dict, models: dict, *, dry_run: bool, timeout: int) -> dict:
    """Grade the content trial: mechanical facts in code + a blind model grader for voice."""
    mech = mechanical_content(candidate)
    if dry_run:
        raw = stub_grader_output(candidate, mech)
    else:
        raw = run_via_teamclaude(models["grader"], build_grader_prompt(test, candidate, mech), timeout=timeout)
    verdict = parse_grader_score(raw)
    return {"score": verdict["total"], "grader_raw": raw, "grader_subscores": verdict["subscores"],
            "grader_notes": verdict.get("notes", ""), "mechanical": mech}


# ======================================================================================
# Dry-run stub outputs  (deterministic; exercise the whole grading pipeline w/o teamclaude)
# ======================================================================================
# Clearly synthetic. They are authored to fire specific detectors so the scoresheet shows
# all branches: Opus wins coding decisively, Fable wins content, architecture is a near-tie
# (Fable higher but below the 1.5 threshold). NOT real model data.
STUB_CODING = {
    "opus": """Two defects.

Line 43 (checkout_vip): the flat coupon literal is 5, i.e. 5 cents, but the comment
says "$5.00 off". The dollars-to-cents migration was missed here. Contrast line 39,
which is correct at 500. Fix: value_cents: 500.

Line 56 (format_receipt): it prints ${total:.2f} but total is already in cents, so the
Total line is 100x too large. Lines 54-55 divide by 100 correctly; line 56 does not.
Fix: f"Total:    ${total / 100:.2f}".

Coupon call-sites:
- line 35 checkout_standard: percent 1000 bps = 10%. correct.
- line 39 checkout_flat5: flat 500 cents = $5.00. correct.
- line 43 checkout_vip: flat 5 cents. incorrect, should be 500.
- line 47 checkout_clearance: percent 2500 bps = 25%. correct.

Note: line 18 uses // 10000 to floor the percentage discount to whole cents. In an
all-integer-cents system this is by design and correct, not a bug.""",
    "fable": """Found an issue.

Line 43 (checkout_vip) passes value_cents: 5, which is 5 cents, but the comment says
"$5.00 off". This should be 500. Fix: value_cents: 500.

Call-sites:
- line 35: percent 1000 bps, 10%. correct.
- line 39: flat 500 cents. correct.
- line 43: flat 5 cents. incorrect.
- line 47: percent 2500 bps, 25%. correct.

Also, line 18 uses integer division // 10000, which is a rounding bug: the percent
discount loses fractional cents and should be rounded properly.""",
}
STUB_ARCH = {
    "fable": """Three problems, and they compound.

1. No idempotency. Delivery is at-least-once and retries resend the same event_id, but
   the handler never records processed event ids, so a redelivered payment.succeeded
   credits the user a second time — duplicate store credit. Fix: a unique constraint /
   primary key on event_id; insert it in the same transaction as the credit and skip on
   conflict (ON CONFLICT DO NOTHING).

2. Lost-update race. Steps b and c are a non-atomic read-modify-write with no lock; two
   concurrent events for one user interleave and one increment is lost. Fix: a single
   atomic statement, UPDATE credits SET balance = balance + :amount, or SELECT ... FOR
   UPDATE.

3. Synchronous email breaks the ack window. Step d takes 6-8 seconds, so the handler
   exceeds the provider's 5 second window; that timeout is what triggers the retries,
   which then duplicate the credit. Fix: commit, return 200 immediately, and enqueue the
   receipt to an async worker.

The chain: the slow email causes the 5s miss, the retries resend, and without dedup and
the atomic update those retries double-credit.""",
    "opus": """Issues found.

1. Idempotency is missing. With at-least-once delivery, a resent event_id is processed
   again and credits the user twice. Fix: unique constraint on event_id, insert in the
   same transaction as the credit, ON CONFLICT DO NOTHING.

2. Race condition on the balance. The SELECT then UPDATE (b, c) is a non-atomic
   read-modify-write; concurrent events lose an increment. Fix: UPDATE credits SET
   balance = balance + :amount, or SELECT ... FOR UPDATE.

3. The email call is synchronous and slow (6-8s). Move it to an async worker and return
   200 after commit so the request is fast.

4. Also verify the webhook signature in the handler; you should not assume the request
   is authentic.""",
}
STUB_CONTENT = {
    "fable": ("Meet Beam One, the desk lamp that keeps pace with your work. Choose from four "
              "brightness levels for any task. It charges over USB-C and reaches full power in 90 "
              "minutes. On the lowest level, you get up to 18 hours of light. The matte aluminum "
              "body folds flat for travel. Your purchase is backed by a 1-year warranty. "
              "Set the light, get to work."),
    "opus": ("The Beam One desk lamp offers four brightness levels. It charges over USB-C. A full "
             "charge takes 90 minutes. On the lowest level, runtime is up to 18 hours. The body is "
             "matte aluminum. The body folds flat. You get a 1-year warranty. You can adjust the "
             "light for your task. Set the light, get to work."),
}


def stub_taker_output(test_id: str, arm: str, run_idx: int) -> str:
    tables = {"coding": STUB_CODING, "architecture": STUB_ARCH, "content": STUB_CONTENT}
    table = tables.get(test_id)
    if table is None:
        return f"[stub output for {test_id} / {arm} / run {run_idx}]"
    return table[arm]


def _stub_voice(text: str) -> float:
    """Text-only voice heuristic (blind — no arm identity): variety up, choppiness down."""
    sents = _sentences(text)
    firsts = [s.split()[0].lower() for s in sents if s.split()]
    variety = len(set(firsts)) / max(1, len(firsts))
    short_frac = sum(1 for s in sents if _wc(s) < 7) / max(1, len(sents))
    return round(_clamp(3.0 * variety - 1.5 * short_frac, 0.0, 3.0), 2)


def stub_grader_output(candidate: str, mech: dict) -> str:
    """Mimic a blind grader's reply: mechanical subscores from code + a text-only voice score.

    Blind by construction (arm identity is never an input). Wrapped in a ```json fence with
    a lead-in line to exercise the robust extraction in parse_grader_score.
    """
    voice = _stub_voice(candidate)
    subs = dict(mech["subscores"])
    subs["voice"] = voice
    total = round(sum(subs.values()), 2)
    obj = {"length": subs["length"], "facts": subs["facts"], "no_fabrication": subs["no_fabrication"],
           "formatting": subs["formatting"], "voice": voice, "total": total,
           "notes": "stub grader (dry-run): mechanical from code, voice from text heuristic"}
    return "Here is my assessment.\n```json\n" + json.dumps(obj) + "\n```"


# ======================================================================================
# Administration + scoring
# ======================================================================================
ARMS = ("fable", "opus")


def administer(test: dict, arm: str, run_idx: int, models: dict, out_dir: Path,
               *, dry_run: bool, timeout: int) -> tuple[str, Path]:
    """Run one (test, arm, run); save raw output; return (text, path). Taker sees prompt only."""
    prompt = taker_view(test)["prompt"]
    if dry_run:
        text = stub_taker_output(test["id"], arm, run_idx)
    else:
        text = run_via_teamclaude(models[arm], prompt, timeout=timeout)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{test['id']}-{arm}-{run_idx}.txt"
    path.write_text(text + "\n")
    return text, path


def grade_one(test: dict, arm_texts: dict, models: dict, *, dry_run: bool, timeout: int) -> dict:
    """Grade one candidate output for a test, dispatching by grader kind."""
    if test["id"] == "coding":
        return grade_coding(arm_texts)
    if test["id"] == "architecture":
        return grade_architecture(arm_texts)
    if test["id"] == "content":
        return grade_content(arm_texts, test, models, dry_run=dry_run, timeout=timeout)
    # unknown test -> no automatic grader
    return {"score": None, "breakdown": [], "note": "no grader bound for this test id"}


def paired_wins(fable_scores, opus_scores):
    f = o = tie = 0
    for a, b in zip(fable_scores, opus_scores):
        if a > b:
            f += 1
        elif b > a:
            o += 1
        else:
            tie += 1
    return f, o, tie


def mean(xs):
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(sum(xs) / len(xs), 2) if xs else None


CLEAR_GAP = 1.5  # owner-adjustable: mean gap (/10) Fable must exceed to "clearly beat"


def run_trials(tests, models, out_dir, k, *, dry_run, timeout, seed):
    rng = random.Random(seed)
    results = []
    for test in tests:
        per_arm = {arm: {"scores": [], "paths": [], "grades": []} for arm in ARMS}
        ab_map = []
        for run_idx in range(1, k + 1):
            texts = {}
            for arm in ARMS:
                text, path = administer(test, arm, run_idx, models, out_dir,
                                        dry_run=dry_run, timeout=timeout)
                texts[arm] = text
                per_arm[arm]["paths"].append(str(path))
            # blind A/B: randomize label per run, record the mapping SEPARATELY from grading
            labels = ["A", "B"]
            rng.shuffle(labels)
            mapping = {labels[0]: ARMS[0], labels[1]: ARMS[1]}
            ab_map.append({"run": run_idx, "A": mapping["A"], "B": mapping["B"]})
            # grade each arm's output independently (graders never receive arm identity)
            for arm in ARMS:
                g = grade_one(test, texts[arm], models, dry_run=dry_run, timeout=timeout)
                per_arm[arm]["scores"].append(g["score"])
                per_arm[arm]["grades"].append(g)

        f_mean, o_mean = mean(per_arm["fable"]["scores"]), mean(per_arm["opus"]["scores"])
        gap = round(f_mean - o_mean, 2) if (f_mean is not None and o_mean is not None) else None
        fw, ow, tw = paired_wins(per_arm["fable"]["scores"], per_arm["opus"]["scores"])
        clearly_beats = bool(gap is not None and gap >= CLEAR_GAP and fw > ow)
        results.append({
            "id": test["id"], "axis": test["axis"],
            "fable_scores": per_arm["fable"]["scores"], "opus_scores": per_arm["opus"]["scores"],
            "fable_mean": f_mean, "opus_mean": o_mean, "gap": gap,
            "paired_wins": {"fable": fw, "opus": ow, "tie": tw}, "clearly_beats": clearly_beats,
            "ab_map": ab_map,
            "fable_grades": per_arm["fable"]["grades"], "opus_grades": per_arm["opus"]["grades"],
            "paths": {"fable": per_arm["fable"]["paths"], "opus": per_arm["opus"]["paths"]},
        })
        # record the A/B map to its own file so the blind stays a blind
        (out_dir / f"{test['id']}-abmap.json").write_text(json.dumps(ab_map, indent=2) + "\n")
    return results


# ======================================================================================
# Recommendations (PRINT ONLY — never writes providers.json)
# ======================================================================================
# axis id -> (providers.json prowess key, human note about the home it would grant)
AXIS_PROWESS = {
    "coding": ("code", "non-gating coding-completeness assist (still banned as daily coder; still OUT of gating)"),
    "content": ("content", "brand-voice generation — NEW function: also add 'content' to fable-5.functions and to function_vocabulary"),
    "architecture": ("architecture", "architecture/design critique — Fable's ONLY current home"),
}


def recommend(results):
    prov = _safe_providers()
    fable = prov.get("providers", {}).get("fable-5", {})
    cur_prowess = fable.get("prowess", {})
    recs = []
    for r in results:
        key, note = AXIS_PROWESS.get(r["id"], (r["id"], ""))
        cur = cur_prowess.get(key)
        suggested = int(round(_clamp((r["fable_mean"] or 0) * 10, 0, 100))) if r["fable_mean"] is not None else None
        rec = {"axis": r["axis"], "id": r["id"], "prowess_key": key, "current": cur,
               "earns_seat": r["clearly_beats"], "gap": r["gap"],
               "paired_wins": r["paired_wins"], "suggested_prowess": suggested, "note": note}
        if r["clearly_beats"]:
            rec["edit"] = f'set providers.providers.fable-5.prowess["{key}"] = {suggested}  (was {cur!r})'
        else:
            if r["id"] == "architecture" and cur is not None:
                rec["edit"] = (f'NO edit needed to earn a seat. NOTE: architecture is Fable\'s only current '
                               f'home (prowess["architecture"]={cur}) yet it did NOT clearly beat Opus here — '
                               f'consider lowering or dropping that home. Owner decides.')
            else:
                rec["edit"] = f'no change — leave providers.providers.fable-5.prowess (key "{key}" currently {cur!r})'
        recs.append(rec)
    return recs


# ======================================================================================
# Output
# ======================================================================================
def print_scoresheet(results, recs, models, out_dir, k, dry_run, seed):
    mode = "DRY-RUN (stub outputs — NOT real model data)" if dry_run else "LIVE (teamclaude)"
    print(f"FABLE-EVAL  k={k}  mode={mode}  seed={seed}")
    print(f"arms via teamclaude: fable={models['fable']}  opus={models['opus']}")
    print(f"blind voice grader (non-Fable): {models['grader']}")
    print(f"raw outputs + A/B maps: {out_dir}")
    print("=" * 90)
    print(f"{'Axis':<34}{'Fable':>7}{'Opus':>7}{'Gap':>7}  {'wins F-O-T':<12}{'clearly beats?':>15}")
    print("-" * 90)
    for r in results:
        wins = f"{r['paired_wins']['fable']}-{r['paired_wins']['opus']}-{r['paired_wins']['tie']}"
        gap = f"{r['gap']:+.2f}" if r["gap"] is not None else "  n/a"
        verdict = "YES" if r["clearly_beats"] else "no"
        axis = r["axis"] if len(r["axis"]) <= 33 else r["axis"][:32] + "…"
        fm = f"{r['fable_mean']:.2f}" if r["fable_mean"] is not None else "n/a"
        om = f"{r['opus_mean']:.2f}" if r["opus_mean"] is not None else "n/a"
        print(f"{axis:<34}{fm:>7}{om:>7}{gap:>7}  {wins:<12}{verdict:>15}")
    print("-" * 90)
    print(f'"clearly beats" = mean gap >= {CLEAR_GAP} AND Fable wins a majority of paired runs.')
    print()
    print("per-run scores:")
    for r in results:
        print(f"  {r['id']:<13} fable={r['fable_scores']}  opus={r['opus_scores']}")
    print()
    print("RECOMMENDED providers.json EDITS  (PRINT ONLY — another lane owns the write; land separately)")
    print("-" * 90)
    for rec in recs:
        head = "EARNS SEAT" if rec["earns_seat"] else "NO SEAT"
        print(f"  [{head}] {rec['axis']}")
        sug = f"  suggested prowess[{rec['prowess_key']}]={rec['suggested_prowess']}" if rec["earns_seat"] else ""
        print(f"      gap={rec['gap']:+.2f} wins(F-O-T)={rec['paired_wins']['fable']}-"
              f"{rec['paired_wins']['opus']}-{rec['paired_wins']['tie']}{sug}")
        print(f"      -> {rec['edit']}")
        if rec["earns_seat"]:
            print(f"         ({rec['note']})")
    print("-" * 90)
    earned = [r["axis"] for r in results if r["clearly_beats"]]
    if earned:
        print(f"OVERALL: Fable clearly beats Opus 4.8 on {len(earned)} of {len(results)} axes -> "
              f"earns a non-gating generation seat on: {', '.join(earned)}.")
    else:
        print(f"OVERALL: Fable clearly beats Opus 4.8 on 0 of {len(results)} axes -> no generation seat earned.")
    print("Reminder: GENERATION trials only. Fable stays OUT of the gating/refusal order and out of")
    print("dispatch (owner ruling 2026-08-25) regardless of any result above. A seat here is a")
    print("non-gating generation home, nothing more.")


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Administer + blind-grade the 3 clean-room Fable placement trials via teamclaude.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Real run on the Mini:  bin/fable-eval.py --tests <path/to/fable-tests.md> --k 3\n"
               "Prove the pipeline:     bin/fable-eval.py --dry-run\n"
               "teamclaude command is edited in run_via_teamclaude() (or via $TEAMCLAUDE_BIN/$TEAMCLAUDE_ARGV).",
    )
    ap.add_argument("--tests", default=None, help="path to fable-tests.md or a .json sidecar")
    ap.add_argument("--k", type=int, default=3, help="runs per arm per test (default 3; protocol wants >=3)")
    ap.add_argument("--dry-run", action="store_true",
                    help="use deterministic stub outputs instead of teamclaude (proves the pipeline)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--out-dir", default=None, help="override raw-output dir (default: data_dir/fable-eval)")
    ap.add_argument("--seed", type=int, default=1, help="seed for A/B labelling + stub jitter (reproducible)")
    ap.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="per-call teamclaude timeout (s)")
    ap.add_argument("--fable-model", default=None, help="override the Fable arm model id")
    ap.add_argument("--opus-model", default=None, help="override the Opus arm model id")
    ap.add_argument("--grader-model", default=None, help="override the blind voice grader model id (non-Fable)")
    ap.add_argument("--build-sidecar", nargs="?", const="__default__", default=None,
                    metavar="PATH", help="parse the .md and write a fable-tests.json sidecar, then exit")
    ap.add_argument("--prompts-only", action="store_true",
                    help="with --build-sidecar, also write a taker-safe prompts-only file")
    args = ap.parse_args(argv)

    if args.k < 1:
        raise SystemExit("fable-eval: --k must be >= 1")

    tests_path = resolve_tests_path(args.tests)

    # --build-sidecar: extract md -> json (must be given a .md) and exit
    if args.build_sidecar is not None:
        if tests_path.suffix != ".md":
            raise SystemExit("fable-eval: --build-sidecar needs a .md source (pass --tests <fable-tests.md>)")
        out = Path(args.build_sidecar).expanduser() if args.build_sidecar != "__default__" \
            else tests_path.with_suffix(".json")
        written = build_sidecar(tests_path, out, args.prompts_only)
        print("wrote: " + ", ".join(str(w) for w in written))
        return 0

    tests = load_tests(tests_path)
    # sanity: three known trials expected; warn (don't fail) if the axes look unfamiliar
    known = {"coding", "content", "architecture"}
    got = {t["id"] for t in tests}
    if not known.issubset(got):
        print(f"fable-eval: WARNING — expected trial ids {sorted(known)}, parsed {sorted(got)}. "
              f"Deterministic graders bind to coding/architecture; unknown ids score None.",
              file=sys.stderr)

    models = resolve_models(args)

    if not args.dry_run and not teamclaude_available():
        raise SystemExit(
            f"fable-eval: teamclaude binary {TEAMCLAUDE_BIN!r} not found on PATH — this must run on the\n"
            f"teamclaude-equipped machine (the Mini). To exercise the parse/grade/scoring pipeline here\n"
            f"without teamclaude, re-run with --dry-run. (Override the binary name with $TEAMCLAUDE_BIN.)"
        )

    out_dir = Path(args.out_dir).expanduser() if args.out_dir else (mborch.data_dir() / "fable-eval")
    results = run_trials(tests, models, out_dir, args.k, dry_run=args.dry_run,
                         timeout=args.timeout, seed=args.seed)
    recs = recommend(results)

    if args.json:
        review_order = _safe_providers().get("review_order", [])
        print(json.dumps({
            "mode": "dry-run" if args.dry_run else "live",
            "k": args.k, "seed": args.seed, "models": models,
            "out_dir": str(out_dir), "clear_gap_threshold": CLEAR_GAP,
            "fable_in_gating_order": "fable-5" in review_order,  # expected False (out of gating)
            "overall": {
                "axes_total": len(results),
                "axes_earned": [r["axis"] for r in results if r["clearly_beats"]],
                "axes_earned_ids": [r["id"] for r in results if r["clearly_beats"]],
            },
            "results": results, "recommendations": recs,
        }, indent=2))
        return 0

    print_scoresheet(results, recs, models, out_dir, args.k, args.dry_run, args.seed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

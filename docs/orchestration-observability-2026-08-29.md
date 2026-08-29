# Orchestration decision logging and improvement analytics

Date: 2026-08-29
Scope: append-only, privacy-safe telemetry for routing quality — not a new seat, not a new authority
Status: implemented in this worktree; live executor remains gated/dry-run only

## Decision

Routing quality, token efficiency, usage fallback, review outcomes, and missing evidence need
a durable log that admins can fold over time. The existing usage history
(`bin/usage-record.py`) records seat occupancy. The run ledger (`bin/runledger.py`) records
lane lifecycle. Neither one is a privacy-safe, multi-user, versioned *decision* log.

The added surface is:

1. A versioned event schema (`config/observability-event.schema.json`, currently v1) for one
   correlated `run_id`.
2. An append-only JSONL store at `$MB_DATA_DIR/orchestration-events.jsonl` (gitignored),
   with flock-serialized concurrent append, truncated-tail isolation, and skip-corrupt
   reads.
3. Config in `config/monitoring.json` → `observability` (enabled flag, path, retention,
   emit switches, privacy flags that cannot be turned off).
4. `bin/observe.py` to append, prune, validate, and report.
5. Optional emit from `bin/resolve-route.py` and `bin/run-brief.py --dry-run` after the
   routing decision is frozen.

Telemetry **does not** classify, assign, review, or land. A write failure cannot flip
`routing_satisfied` from false to true. A malformed observability block fails
`bin/doctor.py` closed. Missing token/cost fields stay `null`.

## Collection

Each `route_decision` / `run_plan` event records:

| Field | Source |
|---|---|
| requested / effective intake, profile | `dispatcher` |
| fallback used + reason (`recorded_unavailability` or `intake_relay`) | `dispatcher` |
| task class, scale, risk flags, review depth | router |
| implement providers, authors, last-resort flag | `implement` / `authors` |
| review chain, independence groups, review_scope, author exclusion | `review.chain` |
| handoff action, artifact *classes*, restricted/unknown | `handoff` |
| usage tier evidence (recorded ledger only) | dispatcher/review seats |
| duration_ms | local timer |
| terminal status + park_reason_code | `routing_satisfied` / park reason |
| tokens/cost | only when the caller supplies provider-reported numbers |

Later events on the same `run_id` may add `review_verdict`, `test_verdict`, `tokens`, and
`terminal` (fix-loop / retraction counts). Fold is first-wins on `event_id` (idempotent)
and last-non-null on measured sections.

`--actor-id` is an explicit pseudonym. If omitted, the actor is `profile:<profile>`.
`$USER`, `$HOME`, and git identity are never read as identity. Emails and path-like
actor strings are hashed, not stored.

## Privacy boundary

Dropped on write: prompt/task body/diff/credential/customer/PII keys, secret-shaped
strings, emails, absolute user paths. `handoff.requires_user_permission` is forced
`false` so a restricted park cannot spawn a permission loop. Artifact *class names*
(`credentials`, `customer-data`) may appear; contents never do.

Runtime logs are gitignored. Synthetic fixtures are committed at
`model-evals/fixtures/observability/v1-correlated-runs.jsonl`.

## Retention

`observability.retention_days` (default 365, `0` keeps forever). Retention is **not**
applied on emit. Admins run `python3 bin/observe.py prune` (the bounded safe point).
That rewrite uses the same exclusive lock as append, so concurrent writers cannot lose
an accepted event. This is **not** equivalent to `usage-record.py --snapshot`, which
prunes usage history automatically.

CLI vs environment: `--no-record` always wins; `--record` / `--record-observability`
always emit even if `MB_OBSERVABILITY=0`; the env toggle only disables default/config
emit. The append path itself never rewrites except through `prune`.

## Analysis

`python3 bin/observe.py report --json` returns coverage/missingness, routing
success/park/fallback rates, token-per-success *where measured*, usage starvation,
handoff parks, reviewer disagreement, fix-loop and retraction frequency, and
per-role / per-provider / per-actor outcomes.

Every report sets `causal_claim: false` and a disclaimer that these are observational
correlations. `token_per_success` is `null` unless at least one routing-success run
carried provider-reported token totals. Zeros are not invented for missing data.

## Adding a metric for a future model

1. Keep `additionalProperties: true` on the event schema so unknown fields are readable.
2. Record the new field only when a provider or harness actually produced it.
3. Append a synthetic fixture line that includes the field *and* a sibling run where it
   is missing.
4. Extend `bin/observe.py` `analyze()` to display coverage for that field. Do not treat
   it as a cause, and do not impute a default.
5. Add a unit test that a missing value stays `null` and that a future `schema_version`
   still folds.
6. Run `python3 bin/test_observability.py`, `python3 bin/doctor.py --strict`, and
   `python3 bin/smoketest.py --strict`.

Do not change `capability`, `eligibility`, fallback rank, or quality rank because a
correlation appeared in this log. Those remain config + evidence decisions.

## Validation

Automated coverage added:

- schema v1 required fields; unknown/future fields ignored; strict mode rejects unknown kinds
- idempotent `event_id` (timestamp excluded from the fingerprint)
- concurrent append
- truncated and corrupt tail recovery
- redaction of prompts/diffs/secrets and absolute path sanitization
- no inferred personal identity; multi-user reports stay separated by `actor_id`
- missing usage/token fields are not fabricated
- fallback attribution is the recorded requested→effective pair
- restricted handoff parks with `requires_user_permission: false`
- resolve-route / run-brief emit without changing routing fields
- telemetry write failure leaves a park as a park
- malformed observability config fails doctor closed

Required local commands (same set as the intake/handoff audit, plus observability tests):

```text
python3 bin/test_observability.py
python3 bin/test_model_registry.py
python3 bin/test_generate.py
python3 bin/smoketest.py --strict
python3 bin/doctor.py --strict
python3 bin/model-registry.py validate
python3 bin/model-registry.py write-matrix --check
```

Observed results on the implementation worktree:

- `bin/test_observability.py`: 39 tests passed (loop-1 completeness repairs included)
- `bin/test_model_registry.py`: 151 tests passed
- `bin/test_generate.py`: 50 tests passed and seven roles validated
- strict smoke test: 27/27 checks passed
- strict doctor: zero errors and zero warnings
- model-registry validation, generated-matrix check, Python compilation, JSON parsing, and
  `git diff --check`: passed

Related baseline: `docs/dynamic-intake-review-handoff-audit-2026-08-29.md`.

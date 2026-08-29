# Dynamic intake, review, usage fallback, and handoff audit

Date: 2026-08-29
Scope: `mb-orchestration` exact-tip extension following the frontier model role audit
Status: implemented, locally validated, and independently reviewed; live executor remains gated/dry-run only

## Decision

The prior global-dispatcher design was too rigid for multiple users and mixed provider quotas. It
also selected reviewers before recording who dispatched or authored the artifact. That made a
dispatcher/reviewer conflict invisible and forced users to rewrite shared config when changing
their preferred intake model.

The corrected model is:

1. User-selected intake provider wins when it is explicitly dispatch-qualified, bound to a
   `live_verified` route, backed by usable recorded quota, and has passed the dispatch probe.
2. Exactly one effective dispatcher is recorded per run.
3. A valid but unavailable/spent requested provider automatically falls through the configured
   evidence-ranked list. A known non-dispatch intake may relay an ordinary brief to that list without
   gaining authority. Unknown providers park.
4. Implementation prefers another usable coder; this is a quota/separation preference, not an
   absolute ban. Capability gates remain mandatory.
5. Implementers/authors are removed from review candidates.
6. A dispatcher may review an artifact it did not author, but that pass is `artifact-only`. At least
   one different reviewer must independently validate dispatch intent/risk. Cross-family review
   still requires different independence groups and physical invocations.
7. Minimum-necessary ordinary repo artifacts are preauthorized between configured providers.
   Restricted or unknown classes park with `requires_user_permission:false`; authorship never creates
   another permission requirement.

## Dispatch qualification evidence

The same bounded stability probe was run against every valid local dispatch target. Each clean run
had a fixed decision prompt, required a final assignment, checked for reversals/retractions, and
required the process to stop. These were small, single-turn probes, not long-horizon autonomy tests.

| Provider | Clean completed trials | Observed reversals | Qualification | Important caveat |
|---|---:|---:|---|---|
| Codex Luna | 2/2 | 0 | dispatch-capable | Routine coordination prior; not a reviewer/coder |
| Codex Terra | 2/2 | 0 | dispatch-capable | Existing highest dispatch quality prior; MCP volume remains its main role |
| Codex Sol | 2/2 | 0 | dispatch-capable + reviewer | If Sol dispatches, Opus reviews first; Sol review is artifact-only |
| Opus 5 | 2/2 | 0 | dispatch-capable + reviewer | Probe does not disprove user-reported long-session retraction loops |
| Opus 4.8 | 2/2 | 0 | dispatch-capable + review fallback | Time-bounded compatibility route, not normal review-order leader |
| Fable 5 | 2/2 clean retries | 0 | dispatch-capable | First attempt stalled; architecture remains its primary role |
| Grok 4.6 Build | 2/2 | 0 | dispatch-capable + implementer | Non-TTY launcher failed; TTY path completed |

Qualification is machine-readable in each provider's `dispatch_evidence`. Runtime selection and
`doctor.py` both fail closed if the record is missing, incomplete, or has an observed reversal.
Each record binds the provider, route, date, and trial summary to
`model-evals/receipts/2026-08-28-dispatch-stability.json`; invalid/future dates, unapproved paths,
missing files, traversal, and receipt mismatches fail closed.
These results establish basic dispatch viability only. They do not establish a universal quality
ranking, long-horizon stability, or interchangeability across harnesses.

## Fallback and performance order

Explicit user selection outranks the fallback list. Fallback is used only after recorded route or
usage unavailability. Current order is:

1. Codex Terra
2. Opus 5
3. Codex Luna
4. Codex Sol
5. Opus 4.8
6. Fable 5
7. Grok 4.6 Build

The first three preserve the pre-existing dispatch-specific operational quality prior
(`Terra > Opus 5 > Luna`). Remaining entries are stability-qualified fallbacks with role-preservation
penalties: Sol is scarce review capacity, Opus 4.8 is compatibility-only, Fable is architecture
capacity with one stalled attempt, and Grok is primary implementation capacity with a TTY-specific
launcher. This tail order is provisional; it is not presented as a measured head-to-head quality
rank. A future same-harness multi-case dispatch evaluation may change it.

## Review matrix

Expected first reviewer at `single-frontier`, assuming all listed providers are usable and the normal
Grok implementation path authored the artifact:

| Effective dispatcher | First independent reviewer | Dispatcher may also review? |
|---|---|---|
| Codex Sol | Opus 5 | Yes, later and artifact-only |
| Opus 5 | Codex Sol | Yes, later and artifact-only |
| Opus 4.8 | Codex Sol | Yes, later and artifact-only |
| Fable 5 | Codex Sol | Fable is not review-eligible; Opus remains available as Anthropic review |
| Grok Build | Opus 5 | No if Grok authored the artifact; author exclusion wins |
| Codex Terra | Opus 5 | Terra is not review-eligible |
| Codex Luna | Opus 5 | Luna is not review-eligible |

For `cross-family`, resolver selects a second pass with a different independence group and unique
physical invocation. Same-family Opus/Fable combinations never satisfy that gate. If an author
exclusion or outage removes the second family, the gate parks.

## Data-boundary result

`config/handoff-policy.json` distinguishes:

- Ordinary: brief, repo source, diff, test output, public docs, synthetic eval.
- Restricted: credentials, tokens, restricted PII, customer data, production exports.
- Unknown: any new class not yet reviewed by admins.

Ordinary artifacts transfer only between configured selected participants and only at minimum
necessary scope. No additional orchestration permission prompt is produced, even when a receiving
agent previously authored related code. Restricted and unknown classes never auto-transfer and do
not trigger a repeated approval request; the run parks. This policy does not suppress operating
system permissions, provider authentication, repository authorization, publish approvals, or owner
gates for consequential actions.

## Validation performed

Automated gates added or updated:

- every tested dispatch target honors explicit user selection;
- spent requested provider falls back automatically;
- Sol-specific exhaustion cannot borrow the generic Codex intake usage row;
- a recorded Fable downgrade removes that seat from dispatch eligibility;
- unknown identities and malformed/unverified dispatch claims fail closed;
- only a declared non-dispatch entry surface may relay, and it never gains dispatch authority;
- profile selection is per user/run and `profiles.default` is schema-required;
- dispatcher separation never makes metered implementation outrank an included usable route;
- within the same billing class, a usable non-dispatch worker is selected before the dispatcher;
- same-pipe reviewers are artifact-only and cannot validate dispatch intent/risk;
- Sol dispatch routes Opus first and marks Sol artifact-only;
- implementer is excluded from review;
- dispatcher-only review cannot satisfy the independent gate;
- ordinary handoff never prompts and authorship does not alter authority;
- restricted/unknown artifacts park without a permission loop;
- one-to-many example configurations use the new schema.

Required local commands:

```text
python3 bin/test_model_registry.py
python3 bin/smoketest.py --strict
python3 bin/doctor.py --strict
python3 bin/model-registry.py validate
python3 bin/model-registry.py write-matrix --check
```

Observed results on the implementation worktree:

- `bin/test_model_registry.py`: 151 tests passed;
- `bin/test_generate.py`: 50 tests passed and seven roles validated;
- strict smoke test: 26/26 checks passed;
- strict doctor: zero errors and zero warnings;
- model-registry validation, generated-matrix check, Python compilation, JSON parsing, and
  `git diff --check`: passed.

An independent read-only Sol review of the first complete diff returned a six-item fix list. Those
findings were repaired: Fable downgrade-ledger enforcement, economic ordering before dispatcher
separation, complete runtime evidence fields, relay restricted to declared entry surfaces,
fail-closed unknown-intake handoff output, and a required default profile.

The next full-diff review confirmed those repairs and found three novel defects: provider-ID rather
than pipe-based dispatch independence, dispatcher separation that was too weak within included
routes, and evidence fields not bound to structured receipts. All three were repaired. A final
targeted read-only verification returned `VERDICT: SHIP`, confirming the new regressions and the
151-test, 26/26 smoke, strict-doctor, and diff-integrity results.

## Opus 5 reassessment

Prior placement of Opus 5 as the normal Anthropic reviewer remains supported by the earlier
architecture comparison and external evidence recorded in the frontier audit. Treating Opus 5 as a
single global dispatcher was not supported and has been removed. Its two clean bounded dispatch
trials did not reproduce retraction loops, but the test was too short to invalidate the user's
long-session observation. Opus 5 therefore remains a valid selectable/fallback dispatcher, not a
mandatory one. When it dispatches, Sol or another independent provider validates intent/risk.

## Admin expansion procedure

For each new model/provider:

1. Register provider, family, durable level, functions, capabilities, backing usage seat, and route.
2. Keep route non-routable until identity/access/evidence attestations pass.
3. Run the shared dispatch stability harness with at least two clean trials; record completion,
   reversals, runtime requirements, failures, and date. Do not erase failed first attempts.
4. Add `dispatch_evidence` only after passing. `dispatch_eligible` without that record fails doctor
   and runtime qualification.
5. Run role-specific quality and token-efficiency cases. Latency remains weight zero because raw hard
   speed is not the optimization target.
6. Place the model in fallback order based on role-specific evidence, capacity cost, and opportunity
   cost. Do not infer a universal rank from a general leaderboard.
7. Re-run conflict tests for every dispatcher/reviewer/implementer overlap and every usage bucket.
8. Run strict doctor, unit tests, smoke tests, and matrix check; commit the evidence and rationale.

## Remaining limits

- Stability sample is 2 clean trials per provider and single-turn. Long-horizon retraction behavior
  needs a multi-turn contradiction/recovery suite.
- Fable's initial stall and Grok's TTY dependency remain operational risks.
- Opus 4.8 remains time-bounded.
- Live execution is still intentionally gated; `run-brief.py` only plans and records dry-run traces.
- Review E remains unwired and cannot rescue a gate today.

Related baseline: `docs/frontier-model-role-audit-2026-08-28.md`.

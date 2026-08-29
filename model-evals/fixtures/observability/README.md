# Observability fixtures

Committed, synthetic orchestration events. Runtime logs (`data/orchestration-events.jsonl`)
are gitignored; these fixtures are the reviewable contract for schema v1.

They contain **no** prompts, task bodies, diffs, credentials, customer data, or absolute
user paths. Actor ids are explicit pseudonyms (`team-a`, `team-b`), never inferred
identities.

`v1-correlated-runs.jsonl` covers:

- requested vs effective intake, including a recorded-unavailability fallback
- success and park terminals, including usage starvation and a restricted handoff park
- review disagreement, fix-loop and retraction counts, a test verdict
- one run with provider-reported tokens/cost and several with `tokens.measured=false`
- a future `schema_version` with an unknown field that readers must ignore
- two actors so per-user reports cannot be collapsed

Analyze with:

```bash
python3 bin/observe.py --path model-evals/fixtures/observability/v1-correlated-runs.jsonl report --json
```

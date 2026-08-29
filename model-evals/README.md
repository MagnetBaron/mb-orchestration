# Model evaluation runbook

Admin process for live candidate evaluation and normalized receipts. This
directory is **not** a routing table. Cataloging a model does not make it
resolvable. Rankings never grant tools, credentials, write access, publish
authority, or data access.

## Two-phase intake

New models enter in two phases. `config/model-registry.json` encodes the
required promote checklist under `intake.promote_requires`.

1. **Catalog as non-routable.** Add the model and a route with
   `route_state` of `catalog_verified` (official id confirmed) or `unwired`
   (publicly documented, no local harness). It appears in
   `generated/model-matrix.md` and `bin/model-registry.py inventory` but
   `resolve` will not return it.
2. **Promote to `live_verified` only after all of:**
   - official-id verification against the lab catalog
   - local access smoke on the intended host/harness
   - role evals from `cases.json` with normalized JSONL receipts
   - independent evidence (not vendor-only) dated and sourced
   - cost and context-window capture
   - owner/admin approval recorded in the route `evidence` list

Incubation (`incubation: true`) is for vendor-heavy or too-new candidates
(example: GLM 5.3 Flash). It is still non-routable until promotion.

## Running evals

Use the candidate's real CLI on a machine that already has access. Do not
paste secrets into receipts. Do not hit production Shopify/Admin.

```bash
python3 bin/model-eval.py --validate-cases
# produce secret-free JSONL, one object per line, then:
python3 bin/model-eval.py path/to/receipts.jsonl --json
```

Weights (from `cases.json`, overridable there only):

| Signal | Default weight |
|--------|----------------:|
| correctness | 0.70 |
| token efficiency | 0.25 |
| evidence discipline | 0.05 |
| latency | 0.00 |

Latency may be recorded on every receipt. It must not decide ranking.

Synthetic suites that every new coding/review/research candidate should hit:

- `routing_brief_quality`
- `context_compression_recall`
- `defect_review`
- `implementation_planning`
- `evidence_discipline`
- `token_efficiency`

## Receipt shape

```json
{"case_id":"defect-review-1","model":"claude-opus-5","route":"opus-5-teamclaude","output":"...","tokens_in":900,"tokens_out":180,"latency_ms":4200}
```

Gold matching in `cases.json` computes correctness when `correctness` is
omitted. `flags: ["invented_metric"]` zeros the evidence-discipline term.

## After scoring

1. Attach the receipt path and date to the route's `evidence` list.
2. Update per-role `quality` ranks only from the same harness and effort.
   Do not merge scores across harnesses into one global leaderboard.
3. Keep `selection` independent of `quality`. A scarce top model can rank
   first on quality while a cheaper live route remains the default.
4. Run `python3 bin/model-registry.py validate` and
   `python3 bin/model-registry.py write-matrix`.
5. Do not edit `generated/model-matrix.md` by hand.

## What this does not do

- It does not wire connectors.
- It does not change `entrypoints.json` dispatcher authority.
- It does not make Fable a second family for a cross-family gate.
- It does not treat Artificial Analysis or vendor posts as local proof.
- It does not run against live customer data or secrets.

# Fixture recordings (R6)

These files let `make all` and the pipeline tests run before lane R7 writes the real
`config/models.lock.toml` and `recordings/`.

- `items.jsonl` — 20 fake evaluation complaints, valid `Complaint` rows.
- `library.jsonl.gz` — 10 fake past cases, used for the neighbours and the baseline.
- `models.lock.toml` — two fake models, `fixture-primary` and `fixture-comparison`.
- `fixture-primary.jsonl`, `fixture-comparison.jsonl` — one recorded answer per item,
  keyed exactly as `field_return_triage.llm.record.recording_key` (model id, prompt
  version `e1`, canonical messages). They are hand-made, **not** gateway responses.
- `calls.jsonl` — the per-call cost and duration sidecar the runner reads in replay.

One comparison answer (`fx-005`) is deliberately unparseable so the invalid-answer path
is exercised end to end. Costs and durations are fixed, so the metrics and the results
tree are deterministic.

`resolve_paths` uses this directory only when `config/models.lock.toml` is absent; the
run id is `fixture`, and `results/SUMMARY.md` says plainly that these are not model
results. R7 replaces them with the real lock and recordings.

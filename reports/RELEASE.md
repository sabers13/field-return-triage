# Release v1.0.0 - fix-up report (R11)

**Base:** local `main` at `33116e9` (R8 page, R9 docs and R10 review merged).
**Branch:** `fm/frt-r11`. Nothing was pushed and no remote was added.
**Verdict:** ready for the captain to land and tag. `make release-check` is green, and a
full replay rebuild from `recordings/` is byte-identical twice.

The R10 review (`reports/REVIEW.md`) found **0 blockers, 10 should-fix and 4 nits**.
Every should-fix is fixed; three nits remain open with the reasons below. The R8 page
screenshots were checked separately because the review predates R8.

## What was checked

| Check | Result |
| --- | --- |
| `make release-check` (Ruff, format, strict mypy 61 files, 434 tests, forbidden, secrets, facts 26) | green |
| `rm -rf results && make all` from the committed tree, then `make all` again | byte-identical both times (all 12 results files, including `runs/live/schedule.json`) |
| Offline replay (`make all` under `unshare -rn`) | green; no Hugging Face request or retry |
| Offline embedding under `unshare -rn` (`local_files_only=True`) | green, no network attempt |
| `data/CHECKSUMS.txt` | unchanged; 8/8 data files still match |
| `results/MANIFEST.sha256` | regenerated; every results file listed |
| R8 page at 360 px and 1280 px, light and dark | rebuilt page checked in Chrome; no horizontal overflow; 12 queue cards (4/4/4); screenshots saved as release evidence |
| `git status` | only this lane's files; no `.env`, no key, no remote |

The replay rebuild regenerated `cards.jsonl`, `metrics.json`, `SUMMARY.md`,
`page/page-data.json`, `dist/field-return-triage/index.html` and the manifest from the
committed recordings. The data files, recordings, baselines and trend files did not
change.

## Review items

### Should-fix

| Item | Status | What changed |
| --- | --- | --- |
| **S1** `make all` cannot rebuild `results/` from a clean clone | **fixed** | `Makefile`: `index-cached`, `results` and `eval-replay` now run with `--extra index`, so `make all` installs the extra it needs. The embedder's error no longer tells users `make setup` installs the extra. |
| **S2** A mileage quote sends a card to priority 2 | **fixed** | `rules/hard_rules.py`: routing and the "clear clues" reason now count only kept symptom, condition and fault-code quotes (`_clue_quotes`). Mileage and safety quotes remain on the card as support but are not failure clues. Four live cards moved from priority 2 to 3 (the four in the review); needs-human share is now 0.667 (0.620-0.712) primary and 0.460 (0.392-0.529) comparison. Tested in `tests/rules/test_hard_rules.py`. |
| **S3** A dropped clue stays on the card | **fixed** | `build_card` stores a filtered extraction (symptoms, conditions, fault codes, mileage), so the JSON card and `frt triage`'s readable view no longer show a failed clue; a failed safety quote is no longer repeated in the reason text. The safety flag and its quote remain on the extraction because the frozen contract requires a quote whenever the flag is true, and the flag has already made the case priority 1; the reason says the quote failed instead. Tests assert the dropped clue is absent from `card.extraction` and `render_card`. |
| **S4** Summary prints `n/a-n/a` for the base-rate CI | **fixed** | `pipeline/summary.py` reads `ci95` as either a dict (the writer) or a list, and a new test feeds a real `{"low", "high"}` interval. `SUMMARY.md` now prints `32.3% (95% CI 23.6%-42.3%)`. |
| **S5** Final safety recall is 1.000 by construction | **fixed as disclosure** | `SUMMARY.md` now states that the final decision includes the coded crash/fire/injury fields, so a coded case is priority 1 by construction and final recall cannot miss one; model-only is the model's own flag. The metric itself is unchanged, matching PLAN section 6's "final decision" wording. |
| **S6** Replay attempts Hugging Face requests | **fixed** | `similar/embedder.py` loads the model with `local_files_only=True` by default; only `make index` passes `allow_download=True` for the one permitted cold-cache download. Verified under `unshare -rn`: no retry, no warning. |
| **S7** Index cache does not pin the embedding revision | **fixed** | `similar/index.py` stores `revision=EMBEDDING_REVISION` in the cache and refuses a cache with a missing or different revision; the index was rebuilt once with the pin. Tests cover both refusals. |
| **S8** A completed reduced run cannot be resumed | **fixed** | `pipeline/run.py` writes the PLAN section 8 plan to `results/runs/<id>/schedule.json` when the comparison model is cut, and honours it on resume instead of re-estimating the unscheduled items. Replay regenerates the same file from the committed calls, so `rm -rf results && make all` is still byte-identical. The live run's file records 400 primary / 200 comparison. The budget-reduction test now resumes the completed reduced run and asserts no extra call. |
| **S9** An unknown component group is accepted | **fixed** | `pipeline/triage.py` maps a group id outside the loaded `groups.toml` ids to `unclear`, so the hard rules send the card to human reading. Tested with an invented `engine` group. No live card had an unknown group, so no published number changed. |
| **S10** README calls the live-run cost the "whole paid run" | **fixed** | README now says the live evaluation cost USD 1.32254292 and the whole paid run, including probes and smoke rounds, cost USD 1.584697 of the USD 3 cap (`reports/RUN.md`); the facts row is relabelled "Live evaluation cost". |

### Nits

| Item | Status | Reason |
| --- | --- | --- |
| **N1** PII screen is case-sensitive and does not cover names | **open** | The screen is the binding NHTSA spec copied byte for byte. Widening it would drop rows and require re-sampling and a paid re-run; it is a captain decision, not an R11 code change. No complainant contact data or identity was found. |
| **N2** Manifest cost undercounts one repeated paid call | **open (documented)** | The manifest keeps the deduplicated guard figure (1.32254292); `reports/RUN.md` records the true 1.322735 for the live run. Changing the manifest key would change a published figure for no analytical gain. |
| **N3** Quote grounding counts safety and mileage quotes | **open** | Both models score 1.000, so no published number is wrong. Changing the denominator would change the published CI; the review itself calls this a nit and the S2 routing defect is fixed. Recommended follow-up for a future version. |
| **N4** Summary omits the median lead time | **fixed** | `SUMMARY.md` now prints `median lead 70.0 days` beside the alert share. |

### R8 page screenshots

The review predates R8 and does not flag the screenshots. The rebuilt page was checked
in Chrome at **360 px and 1280 px, light and dark**: `scrollWidth` equals `clientWidth`
at 360 px, the queue shows 12 cards (4 priority 1, 4 priority 2, 4 priority 3), the
results tables show the new routing numbers, and the theme toggle works. The four
screenshots (full page, 360 x 30,500 and 1280 x 14,983) are saved as release evidence
at `/home/saber/Projects/firstmate/data/frt-r11/screenshots/`. They are not committed:
they are review evidence, not page assets. The README sentence that claimed they live
under `results/page/screenshots/` and are linked from the page was corrected; the page
ships no images.

## Numbers that changed

Only routing changed, and only through S2:

- Primary needs-human share: 0.660 -> **0.667 (0.620-0.712)**.
- Comparison needs-human share: 0.455 -> **0.460 (0.392-0.529)**.
- Four cards (`11673695`, `11709094` for both models, `11770753`) moved priority 2 -> 3.
- 146 clear-clue reason texts now count failure clues only, not the safety/mileage
  support quotes.
- Every other published number (macro-F1, accuracy, coverage, safety recall/precision,
  quote grounding, precision@5, condition agreement, cost, latency, trend backtest,
  baselines) is unchanged and rebuilds byte-identically.

## Open items for the captain

1. **N1 PII decision** (above): accept the binding spec as-is, or commission a wider
   screen and a new sample/run in a later version.
2. **`pyproject.toml` version** is still `0.1.0` while `CHANGELOG.md` and the tag are
   `1.0.0`. No release artifact is built from the package metadata; bump it in the same
   landing commit if the tag and the package should agree.
3. **Cold model cache:** a truly fresh machine still needs `make index` once to download
   BAAI/bge-small-en-v1.5, as the README quickstart says. Replay is offline-first after
   that; `make all` will stop with a clear "run `make index`" message rather than
   silently downloading.

## Publish steps (the captain runs these, not this task)

1. Land `fm/frt-r11` on local `main` by fast-forward (firstmate's guarded path) and
   create the local tag `v1.0.0` on the landed commit.
2. Add the remote and push `main` and the tag `v1.0.0`.
3. Confirm CI runs `make release-check` on the pushed commit.
4. Publish `dist/field-return-triage/` (the single offline `index.html`) to
   `https://sabersojudi.com/field-return-triage/` and open it once in light and dark at
   360 px to confirm the deployed file matches the committed build.
5. Attach or copy the four release screenshots from
   `/home/saber/Projects/firstmate/data/frt-r11/screenshots/` wherever release evidence
   is kept.

No step above was run by this task: nothing was pushed, no remote was added, and no tag
was created.

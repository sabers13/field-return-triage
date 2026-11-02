# Independent review (R10)

**Reviewed commit:** `43f75b3` ("pipeline: lane report R7") on local `main`, 2026-11-02.
The R9 docs commit (`35619e7`, README/METHOD/CHANGELOG/project-facts) landed on `main`
while this review was running; the review branch is rebased onto it, and the R9 docs are
checked separately in §5. The R8 page is still absent.
**Reviewer:** a fresh worker that wrote none of this code.
**Scope:** the merged tree; R10 owns only this report and changes no other file.

**How I checked.** I cloned local `main` at `43f75b3` into a scratch directory outside the
worktree and confirmed there is no `.env`. I ran `uv sync --locked`, `make release-check`,
`make all` twice over the committed tree, and a full `rm -rf results && make all` rebuild
with and without the optional embedding extra, plus an offline rebuild under
`unshare -rn`. After R9 landed I re-ran the gate on `35619e7` (`release-check` and
`make facts`). I read 50 random committed narratives (seed `1649957092`; 49 library + 1
eval) and scanned all 20,400 with independent regexes. I compared the data files with
which-ai-model's committed copies and the X0 snapshot, re-derived the headline metrics
from `cards.jsonl`, and read the rules and their tests.

**Verdict:** **0 blockers, 10 should-fix, 4 nits.** No PLAN §10 stop rule is met. The
literal clean-clone check in the brief (`make release-check`; `make all` twice over the
committed tree) passes; the stricter replay rebuild is S1.

---

## 1. Checks that pass

### Release gate

From the clean clone with no `.env` and no key, on the R9 tree (`35619e7`):

```
$ make release-check
uv run ruff check .                 All checks passed!
uv run ruff format --check .        122 files already formatted
uv run mypy                         Success: no issues found in 57 source files
uv run pytest -q                    427 passed in 23.23s
uv run python scripts/scan_forbidden.py   scan-forbidden: clean (7 hashes, 200 commits)
uv run python scripts/scan_secrets.py     scan-secrets: clean
uv run python scripts/check_facts.py      facts: 26 checked, all present in the named results files
release-check: green
```

On the R7 tree (`43f75b3`) the same gate was green with 118 files and `facts` a no-op;
R9 added the facts file and the docs.

### Reproducibility

- `make all` twice over the committed tree: identical per-file sha256 and a clean
  `git status`.
- `rm -rf results && make all` with the embedding extra installed: the rebuilt tree is
  byte-identical to the committed tree, twice; `cd results && sha256sum -c
  MANIFEST.sha256` reports all 10 files OK. Re-confirmed on the R9 tree after the rebase.
- The same rebuild inside `unshare -rn` is byte-identical too, but it makes Hugging Face
  metadata requests that fail; see S6.
- Without the embedding extra the *rebuild* fails; see S1. The two no-op runs over the
  committed tree pass because `run_eval` reuses the existing cards and never encodes a
  query.

### Data

- `data/CHECKSUMS.txt`: all 8 files OK.
- `data/eval.jsonl`: 400 rows, 400 unique ids, all `frt` half, received 2025-01-02 to
  2026-10-26, 80 safety-relevant, every group ≥ 20 (21/21/35/50/50/21/127/75).
- `data/library.jsonl.gz`: 20,000 rows, all 2020-01-01 to 2024-12-31, 2,038
  safety-relevant; `data/STATS.md` counts match the files.
- Disjointness: 0 eval ids in which-ai-model's 600-row `data/defect/test.jsonl` (all 600
  are `wam`; all 400 eval ids are `frt`), 0 in its 20,000-row train file, and 0 between
  eval and the library. The halving rule recomputes exactly as the spec says
  (`int(sha256("20261031:" + ODINO), 16) % 2`; 0 = `wam`, 1 = `frt`).
- Column drop: `data/eval.jsonl` and `data/library.jsonl.gz` have exactly the 11
  `Complaint` fields (`component, crash, fire, group, id, injury, make, model,
  model_year, narrative, received`); no `CITY`, `STATE`, `VIN`, `STATE_OF_INCIDENT`,
  `VEHICLE_OPERATOR` or dealer field is present. `data/trend/recalls.csv` has only
  `recall_id, make, model, model_year, group, report_date`. The code path
  (`data/complaints.py:258-274`) builds the contract from kept fields only; tests
  `tests/data/test_single_group.py:82-112` assert identity values cannot reach a written
  file.
- Byte-identical normative files: `data/groups.toml`
  (`3f32dedd...c5c045a`) and `data/nhtsa-spec.toml` (`e1aff0a1...30509aa`) are
  byte-identical to both which-ai-model's `data/defect/` copies and the
  `~/.cache/nhtsa-snapshot/2026-10-31/` source.
- Licence wording: the four quoted sentences in `THIRD_PARTY.md:41-57` match
  `report.md` §1 of the snapshot word for word, and the sha256 values in the tables
  match `nhtsa-spec.toml`. The "public domain / us-pd" conclusion is the source's.
- 50 random narratives: no complainant e-mail, phone number or VIN was present. One
  sample (library id `11328972`) contains a dealer name and a full street address. A
  full-corpus scan of 20,400 narratives found 0 e-mail, 0 phone and 0 VIN matches and
  about 40 real dealer street addresses; a few third-party dealership employee names
  (ids `11297988`, `11299508`, `11298144`) appear in the published text. There is no
  complainant identity or contact data. This is N1.

### Rules

- Safety wins: `rules/hard_rules.py:142` returns `Priority.SAFETY` for the model flag,
  the keyword rule or the coded fields, and `route` re-checks `complaint.coded_safety`
  so a caller cannot pass `safety=False` and demote a coded case. All 117 live cards
  whose complaint has a coded crash/fire/injury flag are priority 1. The branch tests
  are in `tests/rules/test_hard_rules.py` (`test_safety_wins_over_every_other_branch`
  and the coded-field test).
- No close/scrap/return: `DecisionAction` is only `accept`/`change`
  (`contracts.py:125-129`), `TriageCard` has no status field, and
  `tests/rules/test_no_auto_close.py` walks every nested contract, the rulebook API and
  a serialised card. The feedback log stores decisions only.
- Failing quotes are counted and excluded from `card.quotes`, but they still appear on
  the card in other places; see S3.
- Keyword files were committed before the first model result: commit `581db2a`
  ("data: commit the safety and condition keyword lists", 2026-11-01 06:33:33 +0100)
  is an ancestor of the first probe recordings (`d1f146d`, 17:03:26 +0100) and of the
  live results (`d58f46e`, 2026-11-02 03:33:26 +0100).

### Method and numbers

- Metrics recomputed independently from `results/runs/live/cards.jsonl` match
  `metrics.json`: primary macro-F1 0.862529, accuracy 0.840, coverage 0.880; comparison
  macro-F1 0.850705, accuracy 0.840, coverage 0.895. `unclear` is counted wrong; the
  implementation uses 2,000 bootstrap resamples and seed `20261031`
  (`pipeline/metrics.py:44-46, 148-172`); safety uses Wilson intervals.
- Safety: final recall 1.000 / precision 0.358744 (primary), 1.000 / 0.486842
  (comparison); model-only recall 1.000 / precision 0.373832 and 0.569231. See S5 for
  why the "final" recall is structural.
- Backtest: 93 alerts, 35 preceding a recall (37.6%), base rate 30/93 = 32.3% with the
  Wilson interval 23.6%-42.3%, median lead 70.0 days. The rule (`spike.py`) is
  count ≥ 3 and count > the Poisson 99.9% limit of the trailing 26-week mean floored at
  0.5; the join window is 0-365 days; the base-rate draw is one same-series week per
  alert with seed `20261031`. The files and CLI agree; the SUMMARY display does not
  (S4).
- Model lock: `config/models.lock.toml:10-17` names the card's `cheapest` =
  `muse-spark-1.3-contributor`, `most_accurate` = `gemini-4-argon`, and
  `no_model_meets_floor = false`, with `source_commit = f6c9abe8...`. That commit is an
  ancestor of which-ai-model's main and its card has exactly those picks. The lock's
  picker rule string matches the card's `picker_rule`. The lock's per-model caps
  (4096 / 1024) match `results/runs/live/manifest.json`.
- Numbers trace: `results/SUMMARY.md` model and baseline numbers match
  `metrics.json`/`baseline/*.json`; `reports/RUN.md`'s 1.584697 total is the raw
  `recordings/calls.jsonl` sum (1.58008168) plus the two replaced first-round probe
  calls (0.004616), rounded in the per-stage table; the 600 cards are 400 primary +
  200 comparison. The base-rate CI display (S4) and the README's "whole paid run"
  sentence (S10) are the two number problems.
- Scans: forbidden list is byte-identical to which-ai-model's 7 hashes; no secrets in
  `recordings/`, `results/`, `data/` or the tree.

---

## 2. Should-fix

### S1. `make all` alone cannot rebuild `results/` from a clean clone

- **Files:** `Makefile:21-22` (`setup` is plain `uv sync`), `Makefile:36-37`
  (`index-cached` runs without `--extra index`), `Makefile:74-75` (`results` runs
  without it), `Makefile:83` (`all` depends on those targets); `pyproject.toml:23-27`
  puts `sentence-transformers` and `torch` in the optional `index` extra;
  `src/field_return_triage/similar/embedder.py:56-65` raises when that extra is absent;
  `src/field_return_triage/similar/search.py:78` needs the embedder to encode each
  query even when the library index is already cached.
- **Evidence.** In the clean clone after `uv sync --locked` (the documented setup) and
  no extra:

  ```
  $ rm -rf results && make all
  ...
  RuntimeError: the index extra is not installed; run `uv sync --extra index` (or `make setup`) before `make index`
  make: *** [Makefile:75: results] Error 1
  ```

  With `uv sync --extra index` the same command succeeds and two rebuilds are
  byte-identical to the committed tree. The two `make all` runs over the *existing*
  committed results pass without the extra only because `run_eval` finds every card
  already on disk and never computes a query embedding.
- **Mitigation, and why this is a should-fix rather than a blocker:** R9's README
  documents the exact prerequisite: the quickstart is `make setup`, `make index`,
  `make all`, and `README.md:55` says "without it `frt triage` cannot embed the query
  even when the index exists." A user who follows the quickstart has the extra. The
  remaining defect is that the `make all`/`index-cached` target alone is advertised as
  "build it only when missing" but cannot do so; the error is clear, but it should be a
  first-class target check (or `all` should use `uv run --extra index`). R11 can fix
  this in the Makefile.

### S2. A mileage quote counts as a "clue" and sends cards to priority 2

- **Files:** `src/field_return_triage/rules/hard_rules.py:144` routes on
  `quote_check.passed == 0`; `src/field_return_triage/extract/quotecheck.py:55-64`
  increments `passed` for the safety quote, symptoms, conditions, fault codes **and
  mileage**; `src/field_return_triage/rules/hard_rules.py:252-255` then says
  "N clues passed the quote check".
- **Evidence.** Four live cards have no kept symptom, condition or fault code and their
  only passing quote is the odometer value, yet they are priority 2:

  | card id | priority | kept clues | quote |
  | --- | ---: | --- | --- |
  | `11673695:muse-spark-1.3-contributor` | 2 | none | `163,000` |
  | `11709094:muse-spark-1.3-contributor` | 2 | none | `253,000` |
  | `11709094:gemini-4-argon` | 2 | none | `the vehicle mileage was 253,000` |
  | `11770753:muse-spark-1.3-contributor` | 2 | none | `approximately 600,000 miles` |

  `11673695`'s card says `"clear clues: 1 clue passed the quote check"` while its
  suggestion says `"no condition and no specific symptom passed the quote check"`. The
  card's narrative is a mileage-fraud complaint, not a failure clue. Three primary and
  one comparison card are affected; the published `needs_human_share` moves by about
  0.75 and 0.5 points if they are corrected. `METHOD.md:41` also says "a card with
  nothing left is routed to a person", which these cards contradict.
- **What it breaks:** PLAN §4 hard rule 2 says an unclear group **or no clue passing**
  sends a card to human reading; a mileage is supporting information, not a failure
  clue. The routing metric in PLAN §6 is therefore slightly optimistic.
- **Fix direction:** count kept symptom/condition/fault-code quotes (a `clue_passed`
  helper) for the route and the reason, and keep `QuoteCheck.passed` only for the
  quote-grounding denominator if that is the definition chosen (see N3).

### S3. A dropped clue stays on the card in three places

- **Files:** `src/field_return_triage/rules/hard_rules.py:285-293` puts the unfiltered
  `extraction` on the card; `src/field_return_triage/rules/hard_rules.py:91-94` writes
  the model's `safety_quote` into the reason text even when the quote check dropped it;
  `src/field_return_triage/pipeline/triage.py:219-227` renders every
  `extraction.symptoms`/`conditions` clue under "Clues:".
- **Evidence.** Two constructed cards, one with a failed symptom quote and one with a
  failed safety quote, show:

  ```
  # failed-symptom card
  card.quotes                      ('went dark', 'after rain')   # filtered, correct
  card.extraction.symptoms         [('display_fault', 'went dark'),
                                   ('intermittent', 'words not in text')]  # leaked
  render_card(...)                 'Clues: display_fault (went dark), intermittent (words not in text), ...'

  # failed-safety card
  reasons[0].text                  'the model marked the complaint safety-relevant: caught fire'
  ```

  The unit test `tests/rules/test_hard_rules.py:330-337` only asserts the quote is not
  in `card.quotes`; it does not look at `extraction` or the rendered text. The live run
  has quote grounding 1.000, so no committed card currently shows it. `METHOD.md:37-38`
  says "The card shows only quotes that passed", which the JSON and the triage view
  contradict for a dropping answer.
- **What it breaks:** PLAN §4 says a failing clue is "dropped from the card and
  counted". The JSON card and `frt triage`'s readable view both show the paraphrase.
  `frt review` filters by `clue.quote in card.quotes` (`rules/cli.py:121-122`), so the
  review CLI and the triage CLI disagree about what is on the card.

### S4. The summary prints `n/a-n/a` for the base-rate 95% CI

- **Files:** `src/field_return_triage/pipeline/summary.py:227-233` expects
  `base_rate.ci95` to be a **list** (`interval[0]`, `interval[1]`), while
  `src/field_return_triage/trend/backtest.py:176-180` writes a **dict**
  (`{"low": ..., "high": ...}`).
- **Evidence:** `results/SUMMARY.md:57` says
  `Base rate for random same-series weeks: 32.3% (95% CI n/a-n/a)`, while `make all`
  prints `base rate 32.3% (95% CI 23.6%-42.3%)` and
  `results/trend/backtest.json` contains
  `"ci95": {"high": 0.422987, "low": 0.236249}`. The JSON is right; the reader of the
  summary is not given the interval that TASKS R5 asked for.
- **Fix direction:** read the dict (or make the writer and reader agree) and add a
  summary test with a real `base_rate.ci95`.

### S5. The "final" safety recall is 1.000 by construction

- **Files:** `src/field_return_triage/rules/hard_rules.py:142` makes
  `complaint.coded_safety` a direct input to `route`; `src/field_return_triage/pipeline/metrics.py:234-235`
  scores `card.priority is Priority.SAFETY` against the same
  `complaint.coded_safety`.
- **Evidence:** 80 of 80 primary cards with a coded crash/fire/injury flag are priority
  1 (37 of 37 for the comparison), so final recall is exactly 1.000 in
  `results/runs/live/metrics.json`. The model-only column is also 1.000 in this run,
  so no published number is false today, but the "final" metric cannot detect a safety
  miss: any coded case is priority 1 whatever the model or keyword rule says.
  `METHOD.md:163` discloses "model flag OR keyword rule OR coded field"; the summary
  line "Final is the hard-rule decision; model-only is the model's own flag" does not.
- **What it means:** PLAN §6's wording is ambiguous ("model OR keyword rule, as used
  by the hard rules"), but as implemented the metric is tautological. Either compute a
  model+keyword-only final variant for the table (keeping final-with-coded as an upper
  bound) or state the construction in `SUMMARY.md`/`RUN.md`. This is a reporting and
  method-honesty issue, not a live-run error.

### S6. Replay attempts Hugging Face network requests

- **Files:** `src/field_return_triage/similar/embedder.py:66-73` loads
  `SentenceTransformer` without `local_files_only=True`; `reports/RUN.md:206-209`
  already records the caveat; `README.md:27-28` and `METHOD.md:228` say the replay path
  uses "no network".
- **Evidence.** A full offline rebuild under `unshare -rn` emitted five retries per
  file before falling back to the cache:

  ```
  'Temporary failure in name resolution' thrown while requesting
  GET https://huggingface.co/api/models/BAAI/bge-small-en-v1.5/tree/5c38ec7c...
  Retrying in 8s [Retry 5/5].
  ```

  With the network available the same rebuild prints
  `Warning: You are sending unauthenticated requests to the HF Hub`.
- **What it breaks:** PLAN §9 says `make all` runs "with no key and no network". It is
  offline-*tolerant*, not offline-*first*; the retries add minutes and the warnings look
  like a failed secret/network check. Use `local_files_only=True`/`HF_HUB_OFFLINE=1`
  for replay (or a documented replay flag).

### S7. The index cache does not pin the embedding revision

- **Files:** `src/field_return_triage/similar/index.py:101-107` stores only
  `model=BAAI/bge-small-en-v1.5` and the data checksum key; `load_index`
  (`index.py:125-130`) checks only the model name; the cache filename is only the data
  checksums (`index.py:38-46`). The module docstring at
  `src/field_return_triage/similar/embedder.py:3-6` says "the revision is part of the
  cache key metadata".
- **Evidence:** `~/.cache/field-return-triage/index-f1cc46e4f69437c4.npz` has keys
  `ids, vectors, model, checksums` and no revision; `EMBEDDING_REVISION` is used only
  when loading the model (`embedder.py:66-70`), never checked on load. A revision bump
  or a different repo at the same model name would silently reuse the old library
  vectors and change every neighbour without a rebuild.
- **Fix direction:** store and verify `EMBEDDING_REVISION`, and include it in the cache
  filename metadata (or refuse a cache whose revision does not match).

### S8. A completed reduced run cannot be resumed for one missing card

- **Files:** `src/field_return_triage/pipeline/run.py:427-445`: `remaining` is every
  item without a card, and the budget guard re-estimates it before any per-item work.
  After the comparison model has been cut to 200 of 400 items, its cards for items
  201-400 do not exist, so a resume estimates those 200 calls again and raises when
  `spent + estimated > 3.0`.
- **Evidence:** `reports/RUN.md:134-140` and `reports/lanes/R7.md` deviation 5 describe
  exactly this: one repair call was made, then the guard stopped the resume at the
  comparison's unscheduled half. The committed run is complete, but the runner is not
  idempotent after a reduced run.
- **Fix direction:** persist the §8 cut (the scheduled item count per model) in the
  run state and treat a reduced model with all scheduled cards as complete; do not
  re-derive the cut from the cards on disk.

### S9. An unknown component group is accepted as a real group

- **Files:** `src/field_return_triage/extract/parse.py:68-71` validates the answer only
  through `Extraction`, whose `component_group` pattern is
  `^[a-z][a-z0-9_]*$` (`contracts.py:192`); `src/field_return_triage/pipeline/triage.py:107`
  uses the loaded `groups` only for the prompt, never to validate the answer.
- **Evidence.** `parse_extraction('{"component_group":"engine", ...}')` returns
  `(Extraction(component_group='engine'), None)`. `route` then treats it as a real
  group: a card with a passing quote is priority 2 ("clear clues") instead of the
  `unclear` → human-reading branch of PLAN §4 hard rule 2. No live card has an unknown
  group (all 600 are in `groups.toml`), so no committed number is wrong.
- **Fix direction:** validate against the loaded group ids in `triage_item` (or pass
  the id set into parsing) and map an unknown id to `unclear` or invalid.

### S10. The README calls the live-run cost the "whole paid run"

- **Files:** `README.md:142` says "The whole paid run cost USD 1.32254292 of its cap."
  That figure is `results/runs/live/manifest.json` `cost_usd`, the live evaluation's
  deduplicated cost. The whole paid work, including the two probes and the two smoke
  rounds, is USD 1.584697 of the 3.0 cap: `reports/RUN.md:147-159` and the raw
  `recordings/calls.jsonl` sum (1.58008168) plus the replaced first-round probe
  (0.004616).
- **Evidence:** `README.md:119` correctly labels the same number "Run cost"; the prose
  line turns it into the whole paid run and understates the spend by USD 0.262154.
  `make facts` passes because the number is present in `manifest.json`; the checker
  cannot see that the sentence changed what the number means.
- **Fix direction:** say "the live evaluation cost USD 1.32254292; the whole paid run,
  including probes and smoke rounds, cost USD 1.584697 of the USD 3 cap" and add the
  total to `project-facts.yml` if it is quoted in the README.

---

## 3. Nits

### N1. The PII screen is case-sensitive and does not cover names

- **Files:** `src/field_return_triage/data/pii.py:30` compiles the spec patterns
  without flags; `data/nhtsa-spec.toml:161` requires an uppercase street suffix;
  `data/nhtsa-spec.toml:153` says narratives from 2022 on are mixed case. R1's lane
  report already documents this (`reports/lanes/R1.md:123-127`).
- **Evidence:** my 50-narrative sample (seed `1649957092`) contains one library
  narrative (id `11328972`) with a dealer name and a full street address. Across all
  20,400 narratives there are about 40 real dealer addresses, and a few dealership
  employee names (ids `11297988`, `11299508`, `11298144`) in the published source text.
  There is **no** complainant name, e-mail, phone or VIN (0 matches for the contact
  patterns), and NHTSA's own `[XXX]` redactions are present in the source.
- **Why a nit:** the screen is the binding spec, copied byte for byte; widening it
  would drop more rows and require re-sampling and a live re-run, which is a captain
  decision, not an R11 fix. If the captain treats dealer/employee names as personal
  data, PLAN §10.2 would make it a blocker; I do not, because the text is published
  business correspondence, not complainant identity.

### N2. The manifest cost undercounts one repeated paid call

- **Files:** `src/field_return_triage/pipeline/run.py:161-177` keys `read_calls` by
  `(model, complaint)`; the live run has 601 rows but 600 unique keys because item
  `11663876` was paid twice after the reboot (`reports/RUN.md:120-140`). The last row
  wins.
- **Evidence:** raw `calls.jsonl` live sum = 1.322735; manifest `cost_usd` and
  `results/SUMMARY.md:12` = 1.32254292 (the last-row value). `reports/RUN.md:153`
  reports the true 1.322735 and the total 1.584697, so the discrepancy is documented;
  the SUMMARY's "Run cost" is the deduplicated guard figure.

### N3. Quote grounding counts safety and mileage quotes as clues

- **Files:** `src/field_return_triage/pipeline/metrics.py:248-252` uses
  `quote_check.checked/passed`; `src/field_return_triage/extract/quotecheck.py:55-64`
  includes the safety quote and the mileage quote in those counts.
- **Evidence:** both models score 1.000 in `results/runs/live/metrics.json` because
  every quote passed, so the published number is not wrong here. The metric's
  definition ("share of extracted clues", PLAN §6) should exclude the safety/mileage
  support quotes, as should the route in S2.

### N4. The summary omits the median lead time

- **Files:** `results/trend/backtest.json` has `alerts.median_lead_days = 70.0`, but
  `src/field_return_triage/pipeline/summary.py:234-247` prints only the alert count,
  the share and the base rate. PLAN §6 lists the median lead time as part of the
  backtest report; the JSON has it, the one-page summary does not.

---

## 4. Scope notes (not findings against R7)

- R9 has landed on `main` at `35619e7`; the review branch is rebased onto it and its
  docs were checked (release gate, `make facts` 26/26, README numbers). R8 (page,
  `dist/`, `results/page/`, screenshots) is still open, so PLAN §11 as a whole is not
  yet met by this commit; that is expected from the wave plan and is not counted as an
  R7 defect.
- `reports/REVIEW.md` is the only file this lane owns and changes.
- `make facts` now checks 26 numbers against the named files and passes. It checks that
  each number string appears in the named file, not that the surrounding sentence
  describes it correctly (S10).
- The reproducibility check used the warm embedding cache at
  `~/.cache/field-return-triage/index-f1cc46e4f69437c4.npz` (key
  `sha256(data/CHECKSUMS.txt)[:16]`); I did not rebuild it because R3's lane report
  records the one-time ~30-minute build. The cold-cache path is therefore covered only
  by code reading (and S7).
- No PLAN §10 stop rule is met: the licence is as stated; no complainant personal data
  was found (N1); spend is 1.584697 of 3.0; no method change is needed for this
  commit; no policy answer was returned; no key appears in a committed file.

---

## 5. R9 docs (landed after the R7 review)

- `make release-check` on `35619e7`: green (427 tests, Ruff 122 files, mypy 57 source
  files, both scans, `facts: 26 checked`).
- `README.md`'s 16-row facts table and `project-facts.yml`'s bullets resolve to
  `results/SUMMARY.md`, `results/runs/live/manifest.json`, `results/runs/live/metrics.json`,
  `config/budget.toml`, `data/groups.toml` and `pyproject.toml`; `make facts` passes.
- The quickstart (`make setup`, `make index`, `make all`) is correct; `make index`
  installs the CPU extra and downloads the pinned model, and `frt triage
  docs/example-complaint.txt` replays the recorded example. The one sentence at
  `README.md:142` is S10.
- `METHOD.md` correctly describes the flow and the metrics, but its claim that "the card
  shows only quotes that passed" (`METHOD.md:37-38`) and "a card with nothing left is
  routed to a person" (`METHOD.md:41`) is contradicted by S3 and S2 respectively.
- The docs correctly state the model pair, the 200-item comparison cut, the 400-item
  sample and the "agreement, not accuracy" wording.

---

## 6. Evidence summary

| Check | Result |
| --- | --- |
| `make release-check` from a clean clone with no `.env` (R9 tree) | green (427 tests, Ruff 122 files, mypy 57 files, both scans, facts 26) |
| `make all` twice over the committed tree | identical hashes, clean `git status` |
| `rm -rf results && make all` with the index extra | byte-identical to committed, twice; 10/10 manifest hashes |
| `rm -rf results && make all` without the index extra | fails (S1); README documents `make index` first |
| offline `rm -rf results && make all` under `unshare -rn` | byte-identical, with HF retries (S6) |
| data checksums | 8/8 OK |
| eval ids vs which-ai-model test / train / library | 0 / 0 / 0 overlap |
| `groups.toml` / `nhtsa-spec.toml` | byte-identical to both copies |
| licence quotes | 4/4 exact matches to `report.md` §1 |
| 50 random narratives + 20,400 scan | no complainant contact/identity; dealer addresses/names only (N1) |
| safety wins | all 117 coded cards priority 1; branch tests pass |
| no auto-close | contract + AST/serialisation tests pass |
| keyword commit before first model result | `581db2a` (06:33) before `d1f146d` (17:03) and `d58f46e` (next day) |
| model lock vs which-ai-model card at `f6c9abe8` | cheapest / most accurate / floor flag / picker rule match |
| headline metrics | independently recomputed from `cards.jsonl`; match `metrics.json` |
| backtest | 93 alerts, 35 (37.6%), base 30/93 (32.3%, CI 23.6-42.3), median 70 days |
| scans | forbidden 7 hashes identical to which-ai-model; secrets clean |

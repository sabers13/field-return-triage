# Field Return Triage: project plan and frozen method

> **Status: FROZEN at commit 1.** Sections 1–11 are the method, and crewmates never edit them. A change needs the captain. Put any deviation in `reports/DEVIATIONS.md` with the reason, never silently.

## 1. What this project is

**Plain question (the page headline):** *Which returned parts need a closer look, and which test should run first?*

A supplier of electrical and electronic parts receives many returned parts, each with a customer complaint text. Most go through a standard test. When the standard test finds nothing ("no trouble found"), the part often goes back or is scrapped without a finding. A targeted load test is only possible when the complaint gives failure indications: moisture, heat or cold, vibration, intermittent behaviour, a recent repair. Those indications are buried in free text, and there are too many reports to read closely.

This project reads each complaint and, for each one:
1. pulls out the failure clues, each with the exact words it came from;
2. flags safety-relevant cases first;
3. finds similar past cases;
4. suggests the next test with its reasons;
5. watches complaint counts for unusual spikes.

**A technician decides every case.** The AI never closes, scraps or returns a part.

**Data stand-in:** public NHTSA vehicle owner complaints about electrical and electronic components. They are not return reports, but they are the same kind of text a customer complaint contains, and they come with coded component labels and crash/fire/injury flags that make deterministic scoring possible.

The general flow matches the shape of the automotive industry's field-failure analysis practice: a standard test first, a failure-oriented load test when the report gives indications, and a defined handling of "no trouble found". The rulebook here is an example to adapt to a lab's own test catalogue.

Independent portfolio project. It must make sense to someone who has never heard of any particular employer.

## 2. Hard rules (apply to every task)

1. **No employer or person names.** `make scan-forbidden` must pass (hashed list in `config/forbidden.sha256`). Never add the plain tokens anywhere, including commit messages.
2. **No private data.** Location and identity columns are dropped. A narrative that matches the PII screen (§5) is dropped, never redacted.
3. **No secrets in git.** Keys live only in a gitignored env file, referenced as `env:NAME`. They are never printed, logged, traced or recorded.
4. **Paid model calls happen only in R7**, inside the budget in §8. Everything else uses fakes, fixtures or recordings. Tests make zero network calls.
5. **Data only from §5**, credited in `THIRD_PARTY.md`.
6. **Numbers on the page and in the README come only from committed files under `results/`**, rebuilt by `make all`.
7. **No LLM-as-judge.** Every score in §6 is deterministic.
8. **The AI suggests, code checks, people decide.** No code path lets a model output close, scrap, return or down-prioritise a safety-relevant case.
9. Python 3.12, `uv`, Ruff, strict mypy on `src/`, pytest. MIT licence.

## 3. Repository layout

```
src/field_return_triage/
  contracts.py   shared pydantic types (R0, frozen after R0)
  data/          NHTSA fetch, derive, PII screen, splits            (R1)
  llm/           OpenAI-compatible client, record/replay, cost, pacing (R2)
  extract/       extraction prompt, schema, quote check              (R2)
  similar/       embeddings + nearest past cases                     (R3)
  rules/         hard rules, rulebook, triage card, feedback log     (R4)
  trend/         weekly counts, spike rule, recall backtest          (R5)
  pipeline/      triage CLI, evaluation runner, baselines            (R6)
  report/        results export, page data                           (R8)
config/          rulebook.toml, models.lock.toml, prices.toml, budget.toml, forbidden.sha256
data/            committed derived data (§5); data/raw/ gitignored
recordings/      committed, scrubbed model responses (R7)
results/         committed results + MANIFEST.sha256
web/ -> dist/field-return-triage/   static page (R8)
plan/            TASKS.md
```

## 4. The flow

```
complaint text
  └─► 1 Extract (AI)            JSON: component group, safety flag, symptoms, conditions, codes, mileage, each with a quote
      └─► 2 Check quotes (code)  every clue must quote the text verbatim; clues that don't are dropped and counted
          └─► 3 Hard rules (code) safety → priority 1 + human review; unclear or no valid clue → "needs human reading"
              └─► 4 Similar past cases (search)  5 nearest past complaints with their component groups
                  └─► 5 Suggest next step (rulebook)  test(s) + reasons + missing information to request
                      └─► triage card ─► technician decides (accept / change / reason) ─► 6 feedback log
  7 Trend watch (code, separate): weekly counts per make + model + model year + group → spike alerts
```

**Extraction schema** (prompt `e1`, temperature 0, output allowance ≥ 1,024 tokens):
- `component_group`: an id from `groups.toml`, or `unclear`.
- `safety_relevant`: bool, with `safety_quote` (a string, or null).
- `symptoms`: a list of `{kind, quote}`. Kinds: `no_function`, `intermittent`, `warning_light`, `smoke_or_burn`, `noise`, `display_fault`, `battery_drain`, `other`.
- `conditions`: a list of `{kind, quote}`. Kinds: `moisture`, `cold`, `heat`, `vibration_or_road`, `after_service`, `charging`, `speed_or_load`, `startup`, `other`.
- `fault_codes`: a list of `{code, quote}`.
- `mileage`: `{value, quote}`, or null.

**Quote check:** a quote passes when it occurs verbatim in the narrative after whitespace normalisation and case folding. A failing clue is dropped from the card and counted.

**Hard rules (fixed, version `hr1`):**
1. Safety → priority 1 + human review. Safety is the model's `safety_relevant`, OR the keyword rule (§6), OR the coded crash/fire/injury fields when the input has them.
2. `component_group = unclear`, or no clue passes the quote check → "needs human reading".
3. The card always lists its reasons and quotes, plus the model, prompt version, rulebook version and hard-rule version.
4. No automatic close, scrap or return state exists.

**Rulebook (`config/rulebook.toml`, version `rb1`, an example):** condition/symptom kind → suggested test and what to inspect.

| Kind | Suggested test | Inspect |
|---|---|---|
| `moisture` | humidity / condensation test | connectors and seals |
| `cold` | low-temperature operation and temperature cycling | |
| `heat` | high-temperature operation | |
| `vibration_or_road` | vibration test | solder joints and connectors |
| `intermittent` | long-run / power-cycling test with monitoring | |
| `after_service` | check installation, connectors and wiring routing first | |
| `charging` | electrical load and charging-profile test | |

With no conditions and no specific symptom, the suggestion is "standard test; request more information: when it happens, how often, under which conditions, fault codes".

**Feedback log:** `frt review` records the technician's decision per card (accept / change + reason) as JSONL. The page shows the KPI definitions (acceptance rate, change reasons, time to decision) with no invented values.

## 5. Data (binding spec: `data/nhtsa-spec.toml`, copied byte for byte from scout X0)

- **Sources:**
  - NHTSA ODI complaint flat files, received 2020–2024 and 2025–2026;
  - the post-2010 recall file (`https://static.nhtsa.gov/odi/ffdd/`).
- **Licence** as confirmed by X0, with its exact wording in `THIRD_PARTY.md`.
- **Source of truth:** the snapshot's sha256 and dates are recorded. NHTSA rebuilds the files often, so the committed derived files are the source of truth. A fresh download that differs warns and does not stop.
- **Selection:** single-group complaints per `groups.toml` (the same file as which-ai-model's, byte for byte); narrative of at least 80 characters; PII screen per the spec; location and identity columns dropped.
- **Library** (past cases): received 2020–2024, at most 20,000 items stratified by group → `data/library.jsonl.gz`.
- **Evaluation set:**
  - received 2025 or later, `frt` half only, so it is disjoint from which-ai-model's T-DEFECT items;
  - 400 items, seed 20261031, stratified by group, at least 20 per group and at least 80 safety-relevant;
  - → `data/eval.jsonl`.
- **Trend table:** weekly complaint counts per make + model + model year + group, 2020 to the snapshot, counts only → `data/trend/weekly.csv.gz`.
- **Recalls:** recall id, make, model, model year, mapped group and report date → `data/trend/recalls.csv`.

## 6. Method and metrics (fixed before any result exists)

- **Component group:** macro-F1 over groups with `unclear` counted as wrong (the primary metric), with a 95% bootstrap CI (2,000 resamples, seed fixed); accuracy; coverage; accuracy on answered items.
- **Safety:** recall and precision of the final safety decision (model OR keyword rule, as used by the hard rules) against the coded fields, plus the model's own flag alone; Wilson 95% CI. The keyword list is committed by R1 before any model result exists.
- **Quote grounding:** the share of extracted clues whose quote passes the check, per model.
- **Conditions:** agreement of the extracted condition kinds with a fixed keyword rule, reported as **agreement, not accuracy**, since there is no ground truth.
- **Similar cases:** precision@5, the share of the 5 nearest library cases with the same group as the query.
- **Routing:** the share of cards at priority 1 and the share sent to "needs human reading".
- **Cost and speed:** cost per 1,000 items (gateway list cost when present, else tokens × `config/prices.toml`); latency p50/p95.
- **Baselines** (cost 0): TF-IDF + logistic regression on the library for the group; the keyword rule for safety; the keyword rule for conditions.
- **Trend watch (no AI):**
  - Alert when a series' weekly count is at least 3 and exceeds the Poisson 99.9% upper limit of its trailing 26-week mean (the mean is floored at 0.5).
  - **Backtest:** an alert "precedes a recall" when a recall with the same make + model + model year + group has a report date 0–365 days after the alert week.
  - Report: the number of alerts, the share preceding a recall, the median lead time, and the same share for randomly drawn weeks of the same series (seed fixed) as the base rate. **The comparison to the base rate is the headline, never the raw share alone.**

## 7. Model choice (fixed rule)

- Read `results/cards/defect.json` from which-ai-model's main after its live run (task M7).
- **primary** = that card's "cheapest" pick, the cheapest good-enough model that meets the safety floor.
- **comparison** = that card's "most accurate" pick.
- If the card says no model meets the floor, primary = the most accurate model, and the page says plainly that safety rests on the hard rules.
- Both run on the 400 evaluation items.
- `config/models.lock.toml` records the two models and the source: the which-ai-model card path and commit hash.
- All calls go through the captain's OpenCode Go key on the OpenAI-compatible endpoint (`https://opencode.ai/inference/go/openai/v1/chat/completions`). The gateway serves every model there; any model that fails there falls back to its native format, logged in DEVIATIONS.

## 8. Budget

- **R7 hard cap: USD 3** (expected about USD 0.5–1.5).
- The runner estimates cost before each model and stops before the cap. If needed, it reduces the comparison model to 200 items first and logs the cut.
- **Pacing:** at most 2 concurrent requests and 30 requests/minute per model, its own User-Agent, backoff on 429. No time-of-day wait for any model; DeepSeek is called whenever the run reaches it, and its peak or off-peak price is recorded per call.
- Stop on 403, an abuse/policy message or an account warning (§10.5).

## 9. Reproducibility

- Every live response is stored in `recordings/` under `sha256(model id + prompt version + request digest)`. A row holds content and usage only, with no headers.
- `make all` runs in replay mode with no key and no network, and rebuilds `results/` byte-identically (checked by `results/MANIFEST.sha256`).
- Embeddings are recomputed by `make index` (CPU) and cached outside git. Similarity scores are rounded to 4 decimals before ranking, and ties break by complaint id.

## 10. Stop rules (a crewmate writes `reports/STOP.md` and stops)

1. The licence is not as stated, or it restricts redistributing derived extracts.
2. A committed file contains suspected personal data.
3. R7 would exceed the budget even after the §8 reduction.
4. A method change in §6 or §7 seems necessary.
5. The gateway returns 403, an abuse/policy message or an account warning. Stop all live calls; never retry around it.
6. Any key value appears in a file, log, trace or recording.

## 11. Definition of done

- `uv run pytest -q` is green with no network. `make all` in replay mode rebuilds `results/` byte-identically twice in a row.
- `make release-check` is green: lint, mypy, tests, `scan-forbidden`, secrets scan, `facts`, licence files.
- `results/SUMMARY.md` states every headline number with its file.
- `dist/field-return-triage/index.html` works offline (except the GitHub link), at 360 px, light and dark.
- `README.md`, `METHOD.md`, `THIRD_PARTY.md`, `LICENSE` (MIT), `CHANGELOG.md` and `project-facts.yml` are complete.
- Local tag `v1.0.0`. No remote, nothing pushed. The captain inspects and publishes.

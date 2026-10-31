# field-return-triage: task briefs R0–R11

Every brief: first read `PLAN.md` §2 and `AGENTS.md`, and `docs/INTERFACES.md` once R0 has written it. Run `make test` and `make scan-forbidden` before every commit. Finish with `reports/lanes/<ID>.md`. Never push.

---

## R0: Foundation (Wave 0)

The repo exists as an empty local git repo at `projects/field-return-triage` (created by firstmate, no remote).

**Owns:** everything at commit 1 and commit 2.

### Build
1. **Commit 1, `plan: frozen method`.** Copy `PLAN.md` and `AGENTS.md` from `/home/saber/Projects/fm-plan-2026-10-31/field-return-triage/` to the repo root, and `TASKS.md` to `plan/TASKS.md`. Add `CLAUDE.md` containing `@AGENTS.md`.
2. **Commit 2, the scaffold:**
   - `pyproject.toml` (uv, Python 3.12; Ruff, strict mypy and pytest configured as in `projects/which-ai-model`), `.python-version`, `.gitignore` (`.env`, `data/raw/`, caches, `.venv`), `LICENSE` (MIT, Saber Sojudi, 2026).
   - **`src/field_return_triage/contracts.py`** (pydantic, frozen after R0): `Complaint`, `Clue` (`kind`, `quote`), `Extraction` (per PLAN §4), `QuoteCheck`, `Neighbour`, `Suggestion`, `TriageCard`, `Decision` (feedback), `TrendAlert`, `RunManifest` (model settings, prompt version, rulebook version, hard-rule version, sample hash).
   - **CLI stubs** (Typer, `frt`): `frt data`, `frt index`, `frt triage <file|->`, `frt eval --mode replay|record`, `frt review`, `frt trend`. Each stub raises "not built yet (lane Rn)".
   - **Makefile targets** (stubs where a lane builds them): `setup`, `fetch-data`, `data`, `index`, `test`, `lint`, `format`, `typecheck`, `scan-forbidden`, `scan-secrets`, `facts`, `eval-replay`, `live`, `trend`, `results`, `page-data`, `page`, `all`, `release-check`, `clean`.
   - **Scanners and network guard** copied from `projects/which-ai-model`: `scripts/scan_forbidden.py`, `scripts/scan_secrets.py`, the pytest socket guard in `tests/conftest.py`, and the `facts` checker pattern. Credit them in the file headers as "adapted from which-ai-model (same author, MIT)".
   - **`config/forbidden.sha256`** = which-ai-model's file as it is after M0 (including the three v1.1 lines). If M0 has not merged yet, take the current file and append these three lines:
     ```
     e05f05aaf5f3c8caf5a05ad0e9a58cb97de6c36614fe494a1229fd91e0c3f9c9
     50df79aaa0d0b5fb849a6797c8b286681444e5e306b2dba53ddeadf02c1c368d
     9c3125a008064087e6d93acf34289862fd3a625256787183f3b05ed503050809
     ```
   - **`docs/INTERFACES.md`:** the module and function signatures each lane implements, so lanes R1–R5 can work in parallel against fakes.
   - `.github/workflows/ci.yml` running `make release-check` (it runs only once the captain publishes).

### Done when
- [ ] `make release-check` is green on the scaffold.
- [ ] Contract tests pass.
- [ ] Lane report `reports/lanes/R0.md`.

---

## R1: Data (Wave 1; needs X0)

**Owns:**
- `src/field_return_triage/data/`;
- `scripts/fetch_nhtsa.py`;
- `data/` (derived files), except `data/raw/`;
- `tests/data/`;
- the NHTSA rows in `THIRD_PARTY.md`.

**Read first:** `/home/saber/.cache/nhtsa-snapshot/2026-10-31/report.md` and `nhtsa-spec.toml`. They are binding.

### Build
1. Copy `nhtsa-spec.toml` and `groups.toml` byte for byte to `data/`.
2. **Fetch:** use the snapshot when its checksums match; otherwise download to `data/raw/` and warn on a changed checksum.
3. **Derive per PLAN §5:** `data/library.jsonl.gz`, `data/eval.jsonl`, `data/trend/weekly.csv.gz`, `data/trend/recalls.csv`, `data/CHECKSUMS.txt`, and `data/STATS.md` (counts per group, safety rates natural vs sampled, PII drops, recall mapping rate).
4. **`data/safety_keywords.txt` and `data/condition_keywords.toml`** (kind → keywords). Commit them in their own commit, before any model result exists.
5. **`THIRD_PARTY.md`:** the NHTSA complaints and recalls rows, with X0's licence wording, URLs and the snapshot date.

### Tests
- Fixtures only: parsing, column drop, single-group rule, each PII pattern, the halving rule, disjointness from the `wam` half, seed determinism, and trend-table aggregation.

### Done when
- [ ] Derived files and STATS committed.
- [ ] `make test` green.
- [ ] Lane report `reports/lanes/R1.md`.

---

## R2: Extraction and model client (Wave 1)

**Owns:**
- `src/field_return_triage/llm/` and `src/field_return_triage/extract/`;
- `config/prices.toml`, `config/budget.toml`;
- `tests/llm/`, `tests/extract/`.

### Build
- **`llm/` client:**
  - httpx calls to an OpenAI-compatible `/chat/completions`;
  - structured output via JSON schema `response_format` when the endpoint accepts it, else JSON mode plus pydantic validation. Check the OpenCode Go docs (`https://opencode.ai/docs/go/`) and note the result in `docs/GATEWAY_NOTES.md`;
  - retries with backoff on transport errors and 429 (honour `Retry-After`), never on a bad answer;
  - pacing per `config/budget.toml` (2 concurrent, 30/min per model);
  - User-Agent `field-return-triage/1.0 (+https://github.com/sabers13/field-return-triage)`;
  - **policy stop:** a 403 or an abuse/policy/suspension text stops every call and writes `reports/STOP.md`;
  - cost from the gateway's per-response list cost when present, else tokens × prices.
  - Credentials are read only here, from the process environment, then the file named by `FRT_ENV_FILE`, then `.env`. The value is never exposed in `repr`, logs or traces.
- **Record/replay:** key = `sha256(model id \n prompt version \n sha256(canonical JSON of messages))`. Rows hold content, usage and key fields only. Replay mode never touches the network and raises on a miss.
- **`extract/`:**
  - prompt `e1` per PLAN §4: groups with one-line descriptions, the kind lists, "quote the exact words, never paraphrase", `unclear` allowed;
  - the pydantic schema;
  - the quote check (whitespace-normalised, case-folded verbatim match);
  - empty, cut-off or unparseable answers become schema-invalid with the reason, and are never retried.

### Tests
- A fake transport: success, 429 then success, 403 stop, a schema-invalid answer, a quote that fails the check.
- Record then replay gives identical output.
- No key in any `repr` or log.

### Done when
- [ ] `make test` green, mypy strict.
- [ ] Lane report `reports/lanes/R2.md`.

---

## R3: Similar past cases (Wave 1)

**Owns:** `src/field_return_triage/similar/`, `tests/similar/`.

### Build
- Embed the library with the same embedding model and library pin as `projects/which-ai-model/src/which_ai_model/rag/embed.py` (BAAI/bge-small-en-v1.5 on CPU).
  - `make index` writes the vectors to a cache outside git (`~/.cache/field-return-triage/`), keyed by `data/CHECKSUMS.txt`.
  - Downloading the model once is allowed; tests use a fake embedder.
- **Search:** cosine similarity with numpy brute force, top-k with scores rounded to 4 decimals, ties broken by complaint id. Each neighbour carries its id, group, date, safety flag and a 200-character excerpt.
- **Evaluation:** precision@5 against the group, on the eval set.

### Done when
- [ ] Tests green with the fake embedder.
- [ ] `make index` runs on the real library; record its timing in the lane report.
- [ ] Lane report `reports/lanes/R3.md`.

---

## R4: Hard rules, rulebook, triage cards, feedback log (Wave 1)

**Owns:**
- `src/field_return_triage/rules/`;
- `config/rulebook.toml`;
- `tests/rules/`.

### Build
- **Hard rules `hr1`** exactly per PLAN §4, as pure functions over `Extraction` + `QuoteCheck` + the keyword rule + the coded fields.
- **`config/rulebook.toml` `rb1`** per PLAN §4, with a short comment saying it is an example to adapt to the lab's test catalogue.
- **Suggestion builder** (pure function): tests, what to inspect, the information to request, and a reason per suggestion that points at the quote(s).
- **`TriageCard` assembly:**
  - priority (1 = safety, 2 = clear clues, 3 = needs human reading);
  - reasons, quotes, neighbours slot, versions.
  - No field or function can mark a case closed, scrapped or returned (test this).
- **`frt review`:** shows one card in the terminal and records `accept | change <text> | reason <text>` to `data/feedback/decisions.jsonl`. `data/feedback/` is gitignored except an example file.

### Tests
- Every hard-rule branch, including safety winning over everything.
- Rulebook mapping.
- Card assembly.
- The "no auto-close" property.

### Done when
- [ ] `make test` green.
- [ ] Lane report `reports/lanes/R4.md`.

---

## R5: Trend watch and recall backtest (Wave 1)

**Owns:** `src/field_return_triage/trend/`, `tests/trend/`.

### Build
Per PLAN §6, deterministic, no AI:
- **Weekly series** from `data/trend/weekly.csv.gz`.
- **The alert rule:** count ≥ 3 and above the Poisson 99.9% upper limit of the trailing 26-week mean, floored at 0.5.
- **The recall backtest:** same make + model + model year + group, 0–365 days after.
- **The base rate:** random weeks of the same series, seed fixed, same count of draws as alerts.
- **Outputs:**
  - `results/trend/alerts.json`;
  - `results/trend/backtest.json` (alerts, share preceding a recall, median lead time, base-rate share with a 95% CI);
  - `results/trend/example_series.json` (one series with a recall, for the page chart; chosen by a fixed rule: the alert with the longest lead time among series with at least 20 complaints).

If the recall join proves too weak (fewer than 20 alerts with any recall in the window), report that plainly in the backtest file and keep the alerts (can-drop rule).

### Tests
Synthetic series: a spike detected; no spike stays quiet; the boundary values; the backtest window edges; base-rate determinism.

### Done when
- [ ] `make trend` produces the files.
- [ ] Tests green.
- [ ] Lane report `reports/lanes/R5.md`.

---

## R6: Pipeline and evaluation runner (Wave 2; needs R1–R5)

**Owns:**
- `src/field_return_triage/pipeline/`;
- the CLI wiring;
- `tests/pipeline/`;
- `tests/fixtures/recordings/` (fake recordings, 20 items × 2 fake models).

### Build
- **`frt triage <file|->`:** complaint text → extraction → quote check → hard rules → neighbours → suggestion → card (JSON + a readable text view).
- **`frt eval --mode replay|record --models config/models.lock.toml --run-id <id>`:** runs the eval set through the pipeline. It is resumable, uses the budget guard from PLAN §8, and writes `results/runs/<id>/{manifest.json,cards.jsonl,metrics.json}`.
- **Metrics module** per PLAN §6: every metric with its CI.
- **Baselines** per PLAN §6 → `results/baseline/`.
- `make all` = data check → index → trend → results (replay) → page-data → page. It is byte-identical twice.
- `results/SUMMARY.md` generator and `results/MANIFEST.sha256`.

### Tests
- An end-to-end replay on the fixture recordings.
- Byte-identical twice.
- Budget-reduction path and STOP path with a fake clock.

### Done when
- [ ] `make all` works on fixtures.
- [ ] Lane report `reports/lanes/R6.md`.

---

## R7: Live run (Wave 3; needs R6 and which-ai-model M7; the ONLY paid task; cap USD 3)

**Owns:**
- `config/models.lock.toml`;
- `recordings/`, `results/`;
- `reports/RUN.md`.

**Key:** `FRT_ENV_FILE=/home/saber/Projects/which-ai-model/.env`. Never open, print or copy it. `make scan-secrets` runs before every commit.

### Steps
1. Read `projects/which-ai-model/results/cards/defect.json` on which-ai-model's main. Apply PLAN §7 and write `config/models.lock.toml` with both models, the rule, and the card's path and commit hash.
2. Probe one call per model; record the outcome. A model that fails on the OpenAI-compatible endpoint falls back per PLAN §7, logged.
3. **Smoke:** 20 items × 2 models, with the cost estimate for the full run in `RUN.md`; apply the §8 reduction if needed.
4. **Full run:** `make live` (400 items × 2 models, run id `live`), resumable. On 403 or abuse, stop and write `STOP.md`.
5. `make results`. Then delete `results/`, run `make all` with no key and no network, and check it is byte-identical.
6. **`reports/RUN.md`:** the models and why, spend per model against the cap, reductions, deviations, headline metrics, timing.

### Done when
- [ ] Spend ≤ USD 3.
- [ ] The replay check is green.
- [ ] Lane report `reports/lanes/R7.md`.

---

## R8: Page (Wave 4; needs R7)

**Owns:**
- `src/field_return_triage/report/`;
- `web/`, `dist/`, `results/page/`.

### Build
`dist/field-return-triage/index.html` is static and works offline (except the GitHub link), at 360 px, light and dark. Sections:
1. **Headline and the plain question**, plus a 3-sentence "what it does / what it does not do" (a technician decides every case).
2. **The flow diagram** (PLAN §4).
3. **A triage queue:** 12 example cards from the replayed eval set, chosen by a fixed rule (4 priority 1, 4 priority 2, 4 priority 3, by lowest id). Each card shows:
   - the narrative with the quoted clues highlighted;
   - the suggested test with its reasons;
   - the 3 nearest past cases;
   - the versions;
   - demo-only accept/change buttons that store nothing.
4. **Results:** a table per model plus the baselines (macro-F1 with CI, safety recall/precision, quote grounding, needs-human share, cost per 1,000), and which model came from which which-ai-model card.
5. **Trend watch:** the example series chart with alert and recall markers, the backtest against the base rate, and a one-line honest reading.
6. **Limits:**
   - US vehicle complaints stand in for return reports;
   - the coded labels are noisy;
   - the rulebook is an example;
   - condition agreement is not accuracy.

Save screenshots (360 and 1280, light and dark) to the task folder.

### Done when
- [ ] `make page` builds.
- [ ] `make facts` green.
- [ ] Lane report `reports/lanes/R8.md`.

---

## R9: Docs (Wave 4; needs R7)

**Owns:** `README.md`, `METHOD.md`, `THIRD_PARTY.md` (polish), `CHANGELOG.md` (1.0.0), `project-facts.yml`, `docs/` (except INTERFACES).

- **README:** the plain question, a quickstart (`make setup`, `make all` in replay; `frt triage` on one example), the flow, the results headline with files, the limits, and how to adapt the rulebook and groups to your own parts.
- **METHOD:** §4–§7 in plain words.
- `make facts` green.

### Done when
- [ ] `make release-check` green.
- [ ] Lane report `reports/lanes/R9.md`.

---

## R10: Independent review (Wave 4; needs R7; a fresh worker that wrote none of this code)

**Owns:** `reports/REVIEW.md` only.

### Check
1. A clean clone with no `.env`: `make release-check`; `make all` byte-identical twice.
2. **Data:**
   - read 50 random committed narratives for personal data;
   - verify the column drop;
   - verify disjointness from which-ai-model's T-DEFECT ids;
   - verify `groups.toml` and `nhtsa-spec.toml` are byte-identical to which-ai-model's;
   - verify the licence wording matches the source.
3. **Rules:**
   - safety always wins;
   - no code path closes, scraps or returns a case;
   - failing quotes are dropped;
   - the keyword files were committed before the first model result (git log).
4. **Method:**
   - the metrics match PLAN §6;
   - the backtest reports the base rate beside the share;
   - the model lock matches the which-ai-model card.
5. **Numbers** trace to `results/`.
6. **Scans:** forbidden names, secrets.

Write items as **blocker / should-fix / nit**, each with file, line and evidence.

### Done when
- [ ] `REVIEW.md` committed.

---

## R11: Fix-up and release v1.0.0 (Wave 5; needs R8, R9, R10)

**Owns:**
- any file named by a REVIEW blocker;
- `reports/RELEASE.md`.

### Steps
1. Fix every blocker, and the should-fixes that take under 30 minutes each. Rebuild by replay. Mark each review item fixed or open, with the reason.
2. `make release-check`.
3. **`reports/RELEASE.md`:** what was checked, open items, and the publish steps. The captain runs those steps; this task runs none.
4. Create the local tag `v1.0.0` on main.

### Done when
- [ ] The tag exists.
- [ ] No remote, nothing pushed.
- [ ] Lane report `reports/lanes/R11.md`.

# Method

This is the plain-words companion to `PLAN.md` sections 4–7, which are frozen. It
explains what the code does and why, without changing the method. Versions named here
(`e1` prompt, `rb1` rulebook, `hr1` hard rules) are the versions the committed results
were produced with.

The short version: a model reads one complaint and extracts clues; code checks the
quotes, applies fixed safety rules, finds similar past cases and looks up the next test;
a technician decides. Nothing in the pipeline closes, scraps or returns a part.

## 4. The flow

### Step 1 — Extract the clues

One model call per complaint, temperature 0, prompt `e1`. The answer is one JSON object
with every key present:

| Field | Shape | Meaning |
| --- | --- | --- |
| `component_group` | one id from `data/groups.toml`, or `unclear` | which part family the complaint is about |
| `safety_relevant` | `true` / `false` | a crash, fire, smoke, burn, shock or other injury risk is reported |
| `safety_quote` | exact words, or `null` | the words that show the safety risk |
| `symptoms` | list of `{kind, quote}` | what fails: no function, intermittent, warning light, smoke or burn, noise, display fault, battery drain, other |
| `conditions` | list of `{kind, quote}` | when it fails: moisture, cold, heat, vibration or road, after service, charging, speed or load, startup, other |
| `fault_codes` | list of `{code, quote}` | diagnostic trouble codes or other fault numbers named in the text |
| `mileage` | `{value, quote}` or `null` | the failure mileage |

The prompt gives the model the group list with a one-line description each, both fixed
kind vocabularies, the rule to quote exact words and never paraphrase, and permission to
answer `unclear`. The request uses structured output where the gateway supports it; the
answer is validated field by field, and an invalid answer is a result, not a crash.

### Step 2 — Check the quotes

Every quote must occur in the narrative verbatim, after whitespace is normalised and case
is folded. A clue that fails is dropped from the card and counted. The card shows only
quotes that passed, so a technician can always find the words in the complaint.

This is the main defence against a model that invents a plausible clue: an invented quote
cannot pass, and a card with nothing left is routed to a person instead of guessed at.

### Step 3 — Apply the hard rules

The hard rules are fixed code (`hr1`), not a model judgement:

1. **Safety wins.** The model's flag, the committed safety keyword list, or the coded
   crash/fire/injury fields put the card at priority 1 with human review.
2. **Unclear goes to a person.** `component_group = unclear`, or no clue passing the
   quote check, means "needs human reading".
3. **Every card shows its work.** It lists its reasons and quotes, plus the model id,
   prompt version, rulebook version and hard-rule version.
4. **No decision state exists.** There is no close, scrap, return or down-prioritise
   state in the card or the code.

Safety is evaluated first, so no later step can lower it.

### Step 4 — Find similar past cases

The complaint is embedded with the pinned CPU model (`BAAI/bge-small-en-v1.5`, revision
locked in the code) and compared with the library of past complaints. The card carries
the five nearest cases with their component groups and similarity scores. Scores are
rounded to four decimals before ranking and ties break by complaint id, so the list is
deterministic.

Similarity is a search aid, not evidence: the card shows the neighbours, the technician
decides whether they are relevant.

### Step 5 — Suggest the next step

The rulebook (`config/rulebook.toml`, version `rb1`) maps each condition and symptom kind
to the tests to run, what to inspect, and what to ask the customer. For example:

| Clue | Suggested test | Inspect |
| --- | --- | --- |
| moisture | humidity / condensation test | connectors and seals |
| cold | low-temperature operation and temperature cycling | |
| heat | high-temperature operation | |
| vibration or road | vibration test | solder joints and connectors |
| intermittent | long-run / power-cycling test with monitoring | |
| after service | check installation, connectors and wiring routing first | |
| charging | electrical load and charging-profile test | |
| speed or load | load test at the reported speed or load | mounting and thermal behaviour under load |
| startup | cold-start and power-up sequence test | start-up circuit and supply |

With no condition and no specific symptom, the suggestion is the standard test plus a
request for more information: when it happens, how often, under which conditions, and
fault codes. The card gives reasons for every suggestion, so a technician can disagree
with it.

The rulebook is an example. A lab renames the tests to the ones it can run and edits the
kinds it cares about; the code does not depend on the wording, only on the version string.

### Step 6 — The technician decides, and the decision is logged

The card is the end of the automated flow. A technician accepts it or changes it and
gives a reason; `frt review` records that as one JSONL row per card in
`data/feedback/`. The page reports the KPI definitions — acceptance rate, change reasons,
time to decision — and shows no invented values.

### Step 7 — Trend watch, separately

Trend watch makes no model calls. For each series (make + model + model year + component
group) it counts complaints per week. It alerts when a week has at least 3 complaints and
exceeds the Poisson 99.9% upper limit of the trailing 26-week mean (the mean is floored
at 0.5).

The backtest asks whether an alert came before a recall of the same make, model, model
year and group, with a recall report date 0–365 days after the alert week. It reports the
share of alerts that precede a recall **and the share for randomly drawn weeks of the
same series**. The comparison to that base rate is the headline; the raw share alone
would make any noisy series look predictive.

## 5. The data

The pipeline needs complaint text with a component label, plus coded safety fields so the
safety rule can be scored. Public NHTSA ODI vehicle owner complaints provide exactly that
shape. They are not return reports, but they are the same kind of free text a customer
complaint contains, and the public data can be committed and checked.

**Sources and snapshot.** NHTSA ODI complaint flat files for complaints received
2020–2024 and 2025–2026, plus the post-2010 recall flat file. Snapshot date 2026-10-31.
The source files' SHA-256 hashes, URLs, field layouts and the exact licence wording are
in `THIRD_PARTY.md`; the machine-readable copy is `data/nhtsa-spec.toml`. The raw
downloads stay out of git; the derived files are the source of truth, and a later download
that differs warns rather than stops.

**Selection.** A complaint enters the pool when it names exactly one component group
under `data/groups.toml`, its narrative is at least 80 characters, and it passes the PII
screen. Identity and location columns are dropped from every derived file. A narrative
that matches the PII screen is dropped whole, never redacted in place.

**Library.** 20,000 past cases from complaints received 2020–2024, stratified by group.
This is the search corpus for similar cases and the training data for the free group
baseline.

**Evaluation set.** 400 complaints received in 2025 or later, stratified by group with a
minimum per group and safety-oversampled to at least 80 safety-relevant items, seed
20261031. The evaluation items come from the project's `frt` half of the pool, so they are
disjoint from the other project's evaluation half that uses the same public source. The
set is committed once and never tuned against.

**Trend tables.** Weekly counts per make + model + model year + group from 2020 to the
snapshot (counts only), and recall rows whose component maps to a group. The trend table
is not filtered by narrative length or the PII screen because it carries no narrative.

**What is committed.** `data/library.jsonl.gz`, `data/eval.jsonl`,
`data/trend/weekly.csv.gz`, `data/trend/recalls.csv`, `data/STATS.md` (the derivation
record) and `data/CHECKSUMS.txt` (file hashes). `make data-check` verifies the hashes;
`data/STATS.md` holds the funnel and the per-group counts.

## 6. Method and metrics

Every score is deterministic. No model judges another model's output, and every number in
`results/` is rebuilt by replay.

**Component group (primary metric).** Macro-F1 over the groups, with `unclear` counted as
wrong. Macro-F1 averages the per-group F1 scores, so a large group cannot hide a small
one; counting `unclear` as wrong means "I do not know" earns nothing. A 95% bootstrap
interval (2,000 resamples, fixed seed) is reported with accuracy, coverage (the share of
items that got a group other than `unclear`) and accuracy on answered items.

**Safety.** Recall and precision of the final decision (model flag OR keyword rule OR
coded field, as the hard rules use them) against the coded crash/fire/injury fields, with
Wilson 95% intervals. The model's own flag is scored separately so the contribution of
the hard rules is visible. The keyword list was committed before any model result
existed.

**Quote grounding.** The share of extracted clues whose quote passes the check, per
model. It measures whether the model sticks to the text, not whether the clue is useful.

**Conditions.** Agreement between the extracted condition kinds and a fixed keyword rule,
reported as **agreement, not accuracy**. There is no ground truth for conditions, so
agreement is the honest word.

**Similar cases.** Precision@5: the share of the five nearest library cases that have the
query's group.

**Routing.** The share of cards at safety priority 1 and the share sent to "needs human
reading". These are workload numbers, not quality numbers: a cautious system routes more
work to people.

**Cost and speed.** Cost per 1,000 items, using the gateway's own USD list cost when it
reports one and otherwise tokens × `config/prices.toml`. Latency p50 and p95. The paid run
had a hard cap (`config/budget.toml`), and the guard stops before the cap rather than
overspending.

**Baselines (cost 0).** TF-IDF plus logistic regression on the library for the group; the
committed keyword rule for safety and for conditions. A model result is only interesting
next to these.

**Trend watch.** The spike rule above, then the backtest: the number of alerts, the share
preceding a recall, the median lead time, and the same share for randomly drawn weeks of
the same series (fixed seed) as the base rate. The base rate is always reported beside the
share.

## 7. Model choice

The model choice is a fixed rule, not a preference:

- Read the `defect` card from the sibling `which-ai-model` project's main branch after
  its live run.
- **primary** = that card's "cheapest" pick: the cheapest model that meets the card's
  safety floor.
- **comparison** = that card's "most accurate" pick.
- If the card says no model meets the floor, the primary becomes the most accurate model
  and the page says plainly that safety rests on the hard rules.

`config/models.lock.toml` records both models, their roles, temperature 0, output caps
and the exact source path and commit of the card that chose them. Both are called through
one OpenAI-compatible gateway endpoint
(`https://opencode.ai/inference/go/openai/v1/chat/completions`); a model that fails there
falls back to its native format, and the fallback is recorded as a deviation.

The 400 evaluation items run through the primary. The comparison runs as far as the
budget allows: the guard estimates the upper-bound cost before each model and reduces the
comparison set first, never the primary. The committed run cut the comparison to 200
items and records that cut in the metrics and the manifest. The comparison's interval is
therefore wider, and its column is not directly comparable with the primary's.

`config/models.lock.toml` also records the request settings the smoke runs forced:
`reasoning_effort=low` for the primary and different output caps per model. Those are
part of the lock, because a different cap produces different answers.

## Reproducibility

Every live response is committed in `recordings/` under a digest of model id, prompt
version and request. `make all` replays those responses with no key and no network and
rebuilds `results/` byte-identically; `results/MANIFEST.sha256` proves the tree. The
embedding index is rebuilt once by `make index` and cached outside git. Replay is the
default, and the public commands never call a paid model.

The live run's budget, interruptions and the exact spend are recorded in
[`reports/RUN.md`](reports/RUN.md).

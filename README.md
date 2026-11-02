# Field Return Triage

**Which returned parts need a closer look, and which test should run first?**

A supplier receives returned electrical and electronic parts, each with a customer
complaint. Most go through the standard test, many find nothing wrong, and the part is
scrapped or sent back without a finding. A targeted load test is only worth running when
the complaint gives a clue: moisture, heat or cold, vibration, intermittent behaviour, a
recent repair. Those clues are buried in free text, and nobody has time to read every
report closely.

This project reads each complaint and turns it into a triage card: the failure clues with
the exact words they came from, a safety flag, the five most similar past cases, and the
next test to run with its reasons. A technician decides every case. No code path here
closes, scraps or returns a part.

The complaint text is a public stand-in (NHTSA vehicle owner complaints), not real
return data; the rulebook and component groups are examples to adapt to a lab's own
parts.

[Live page](https://sabersojudi.com/field-return-triage/) ·
[Method](METHOD.md) · [Full results](results/SUMMARY.md)

## Quickstart

You need Python 3.12 and [`uv`](https://docs.astral.sh/uv/). The replay path uses no key
and no network; the one-time `make index` step installs the CPU embedding extra and
downloads the pinned embedding model.

```bash
git clone https://github.com/sabers13/field-return-triage.git
cd field-return-triage
make setup       # create the environment from uv.lock
make index       # one-time: CPU embedding extra, model download, library index
make all         # replay: data check, trend, results, summary (no key, no network)
```

`make all` rebuilds `results/` from the committed recordings. Running it twice produces
the same files; `make test` and `make release-check` also run with sockets blocked.

Then put one complaint through the whole flow:

```bash
uv run frt triage docs/example-complaint.txt
```

The command prints the card as JSON and as a readable view: priority and human-review
flag, the quoted clues that survived the quote check, the suggested tests, the five
nearest past cases, and the versions of the model, prompt, rulebook and hard rules.

The example is one of the 400 recorded evaluation complaints, so replay answers it. The
quickstart is replay-only by design: arbitrary text has no recorded model answer and
needs a record run with a key (`frt eval --mode record`).
The `make index` step is also what installs the CPU embedding extra; without it
`frt triage` cannot embed the query even when the index exists.

Check the whole gate the way CI does:

```bash
make test          # pytest, sockets blocked
make release-check # lint, types, tests, name and secret scans, facts, licence
```

## The flow

```
complaint text
  └─► 1 Extract (AI)            one JSON object: component group, safety flag,
      │                         symptoms, conditions, fault codes, mileage,
      │                         each clue with the exact words it came from
      └─► 2 Check quotes (code) every clue must quote the text verbatim;
          │                     clues that do not are dropped and counted
          └─► 3 Hard rules (code) safety → priority 1 + human review;
              │                  unclear or no valid clue → "needs human reading"
              └─► 4 Similar past cases   5 nearest complaints from the library
                  └─► 5 Suggest next step (rulebook)
                      │          tests + reasons + what to ask the customer
                      └─► triage card ─► technician decides
                                        (accept / change + reason) ─► 6 feedback log
  7 Trend watch (code, separate): weekly counts per make + model + model year + group
                                  → spike alerts checked against past recalls
```

Two rules keep the flow honest. The model only extracts; the decision is deterministic
code (`hard rules hr1`) plus a rulebook of test suggestions. And safety always wins: a
safety clue puts the card at priority 1 with human review, whatever else the model says.

`METHOD.md` explains the flow, the data, the metrics and the model choice in plain words.

## Results

The evaluation set is 400 complaints received in 2025–2026, held out from the 2020–2024
library. They are stratified over the eight component groups and deliberately oversample
safety-relevant complaints. Two models ran: the primary on all 400 items, the comparison
on the first 200 because the paid run had a hard cap fixed in `config/budget.toml`. Every
number below is rebuilt from the committed files by `make all`; `make facts` checks each
one against the file named beside it.

<!-- facts:start -->

| Result | Value | File | Proof text |
| --- | --- | --- | --- |
| Primary model macro-F1, 400 items | 0.863 | `results/SUMMARY.md` | `0.863 (0.825-0.895)` |
| Comparison model macro-F1, 200 items | 0.851 | `results/SUMMARY.md` | `0.851 (0.771-0.901)` |
| Safety recall of the final decision | 1.000 | `results/SUMMARY.md` | `1.000 (0.954-1.000)` |
| Safety precision, primary | 0.359 | `results/SUMMARY.md` | `0.359 (0.299-0.424)` |
| Quote grounding, primary | 1.000 | `results/SUMMARY.md` | `1.000 (0.997-1.000)` |
| Similar-case precision@5, primary | 0.823 | `results/SUMMARY.md` | `0.823 (0.805-0.839)` |
| Condition agreement, primary (not accuracy) | 0.915 | `results/SUMMARY.md` | `0.915 (0.905-0.924)` |
| Cards sent to "needs human reading", primary | 0.667 | `results/SUMMARY.md` | `0.667 (0.620-0.712)` |
| Cards at safety priority 1, primary | 0.557 | `results/SUMMARY.md` | `0.557 (0.509-0.605)` |
| Cost per 1,000 items, primary | USD 0.2440 | `results/SUMMARY.md` | `$0.2440 ($0.2372-$0.2512)` |
| Cost per 1,000 items, comparison | USD 6.1247 | `results/SUMMARY.md` | `$6.1247 ($5.8977-$6.3432)` |
| Zero-cost group baseline macro-F1 | 0.415 | `results/SUMMARY.md` | `0.415 (0.396-0.432)` |
| Trend alerts that precede a recall | 37.6% (35 of 93) | `results/SUMMARY.md` | `share 37.6%` |
| Base rate for random same-series weeks | 32.3% | `results/SUMMARY.md` | `32.3%` |
| Evaluation items | 400 | `results/runs/live/manifest.json` | `"item_count": 400` |
| Live evaluation cost | USD 1.32254292 | `results/runs/live/manifest.json` | `"cost_usd": 1.32254292` |

<!-- facts:end -->

What the table says, in words:

- **Component group.** The primary model sorts a complaint into one of eight groups at
  0.863 macro-F1, against 0.415 for a free TF-IDF and logistic-regression baseline.
  `unclear` counts as wrong, so "I do not know" buys no score.
- **Safety.** The final decision reaches recall 1.000: on this sample, every complaint
  with a coded crash, fire or injury flag was flagged. Precision is 0.359, so most
  safety flags are false alarms. That is deliberate — the card sends them to a person
  rather than risking a miss — and it is why safety precision is published beside recall,
  never alone.
- **Grounding.** Every clue on the primary's cards quotes the narrative verbatim
  (1.000 quote grounding). A clue that cannot be quoted is dropped and counted.
- **Similar cases.** 0.823 of the five nearest past cases share the query's group.
- **Condition agreement.** The primary agrees with the fixed keyword rule on 0.915 of
  items. That is agreement, not accuracy: there is no ground truth for conditions.
- **Routing.** 0.667 of the primary's cards land in "needs human reading" and 0.557 at
  safety priority 1. The system hands work to a technician rather than replacing the
  reading.
- **Cost.** The primary costs USD 0.2440 per 1,000 items; the comparison costs USD 6.1247
  and was cut to 200 items. The live evaluation cost USD 1.32254292; the whole paid run,
  including the probes and smoke rounds, cost USD 1.584697 of the USD 3 cap.
- **Trend watch.** 93 spike alerts, 35 of which precede a recall (37.6%), against a 32.3%
  base rate for random weeks of the same series. The comparison to the base rate is the
  headline; the raw share alone would overstate the signal.

The per-model tables, confidence intervals, routing shares, latency and the cost-free
baselines are in `results/SUMMARY.md`; the live run's manifest is in
`results/runs/live/manifest.json`.

## The page

`make all` also builds a single self-contained page into `dist/field-return-triage/`: a
worked example, the triage queue with each card's quoted clues, the measured results and
the method. It ships no images and needs no server; the
[live page](https://sabersojudi.com/field-return-triage/) is that file. No screenshots are
committed; captures of the page belong in `results/page/screenshots/`.

## Limits

- **The data is a stand-in.** NHTSA complaints are public, English, US-market vehicle
  complaints. They are not return reports, not a lab's test results, and not a sample of
  one supplier's parts. The component groups come from NHTSA component labels, not from a
  returns system.
- **400 evaluation items, one snapshot.** Confidence intervals are reported everywhere,
  and they are wide enough that small gaps between models are not meaningful. The
  comparison model ran 200 items, so its interval is wider still and its column is not
  directly comparable with the primary's 400.
- **Safety is oversampled.** The evaluation set deliberately includes more
  safety-relevant complaints than a natural queue would, so safety recall on it is not
  the rate a live queue would see.
- **Most cards still need a person.** 0.667 of the primary's cards land in "needs human
  reading" and 0.557 at safety priority. The system is tuned to hand work to a technician,
  not to replace the reading; a production queue would need the unclear rate brought down.
- **Condition agreement is not accuracy.** There is no ground truth for condition labels,
  so the 0.915 figure is agreement with a fixed keyword rule, not a correctness score.
- **The trend signal is weak.** 37.6% against a 32.3% base rate, with overlapping
  intervals, is a prompt to look, not evidence of a working early-warning system.
- **Replay is the public path.** `frt triage` answers only text with a recorded model
  response. Recording new text needs a key and a budget; nothing here calls a model
  without one.
- **Not a production system.** No queue, no authentication, no audit trail beyond the
  JSONL feedback log. This is a method and a measured example.

## Adapt it to your own parts

Two config files and your own data carry the domain knowledge; none of the code depends
on their wording.

**`data/groups.toml`** — the component taxonomy. Each `[[group]]` has an `id`, a
one-line `description` and the `prefixes` that map a source component label to it. In this
repository the file is a copied normative snapshot and is not edited. In your own copy,
replace the ids, descriptions and prefixes with your own parts: the extraction prompt is
built from this file, so the model sorts into whatever groups it lists. Keep the ids
stable once you have labelled data, and bump `version` when the taxonomy changes.

**`config/rulebook.toml`** — the test suggestions. Each condition or symptom kind maps to
the tests to run, what to inspect, and what to ask the customer. Rename the tests to the
ones your lab can actually run; add or remove kinds with your own failure-analysis
experience. The kind vocabularies are fixed by the extraction schema (`moisture`, `cold`,
`heat`, `vibration_or_road`, `after_service`, `charging`, `speed_or_load`, `startup`,
`no_function`, `warning_light`, `smoke_or_burn`, `noise`, `display_fault`,
`battery_drain`). An unknown kind is a configuration error, not a silent fallback, and
the `other` kinds deliberately fall back to "standard test; ask for more information".
Bump `version` with every change; every card records which rulebook version produced it.

**Your own complaints and labels** — replace `data/eval.jsonl` and the library with your
own records, in the same fields (`id`, `narrative`, `group`, plus the optional coded
flags). Then record model answers once with `frt eval --mode record` and replay them
from then on. The paid path, the model lock (`config/models.lock.toml`), the price table
(`config/prices.toml`) and the budget guard (`config/budget.toml`) are described in
`METHOD.md`.

What does **not** change with configuration: the hard rules (`hr1`) that make safety win
and forbid any close, scrap or return state, the quote check, and the technician's
decision. Changing those is a code and method change, not an adaptation.

## Repository map

| Path | What is there |
| --- | --- |
| `src/field_return_triage/` | the pipeline: data, model client, extraction, similarity, rules, trend |
| `data/` | committed derived data, groups, keyword lists and their checksums |
| `config/` | rulebook, model lock, prices, budget, forbidden-name hashes |
| `recordings/` | committed, scrubbed model responses (one row per call) |
| `results/` | committed run metrics, baselines, trend backtest, summary, manifest |
| `web/` | the page template, styles and fonts |
| `dist/` | the built single-file page |
| `scripts/` | data fetch, facts check and the name and secret scanners |
| `tests/` | the offline test suite |
| `docs/` | the example complaint used in the quickstart |

## Licence and credit

MIT (see [`LICENSE`](LICENSE)). The complaint and recall data are U.S. Government works
in the public domain; the exact source, snapshot, hashes and licence wording are in
[`THIRD_PARTY.md`](THIRD_PARTY.md). The CPU embedding model is BAAI's
`bge-small-en-v1.5` (MIT).

A technician decides every case. No result here closes, scraps or returns a part.

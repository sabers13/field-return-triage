# Live run (R7)

The one paid task in this project: the 400-item evaluation through the two models
locked by PLAN.md section 7, inside a hard cap of USD 3. Every number below comes
from the committed files under `recordings/` and `results/`; the only exception is
the exploratory smoke that left no committed rows, and it is marked as such.

## Models and why

PLAN.md section 7 fixes the rule: primary = the which-ai-model defect card's
"cheapest" pick, comparison = its "most accurate" pick.

- Source card: `which-ai-model:results/cards/defect.json`, commit
  `f6c9abe8d329068030fc88fe3351cb36add35ffc` (that repository's main after its M7
  live run). The lock file records this path and commit.
- **primary** `muse-spark-1.3-contributor` - the card's cheapest good-enough model:
  0.742 macro-F1, 0.975 safety recall, USD 0.089 per 1,000 items.
- **comparison** `gemini-4-argon` - the card's most accurate model: 0.762 macro-F1,
  0.987 safety recall, USD 1.31 per 1,000 items.
- The card says a model does meet its safety floor (`no_model_meets_floor: false`),
  so the primary leads and safety still rests on the hard rules, never on a model
  flag alone.

The lock is `config/models.lock.toml`. Both models are called through the gateway's
OpenAI-compatible endpoint
(`https://opencode.ai/inference/go/openai/v1/chat/completions`).

## Prices

Re-read the OpenCode Go pricing page on 2026-11-01 (PLAN.md section 8 requires the
re-read before a live run). USD per 1,000,000 tokens:

| Model | Input | Output | Note |
| --- | ---: | ---: | --- |
| `muse-spark-1.3-contributor` | 0.10 | 0.20 | contributor price |
| `gemini-4-argon` | 2.00 | 10.00 | 50% launch discount through 2026-11-30 (list 4.00 / 20.00) |

`config/prices.toml` carries the `gemini-4-argon` entry (input and output), as the
note in that file asked when R7 locks the model. Per-call spend is the gateway's own
USD list cost (`usage.opencode.list_cost`), which the client reads before its token
fallback.

## Probe (one call per model)

`make probe` sends the real first-item prompt with the structured-output schema. It
ran twice: once before the reasoning-effort change (2026-11-01T16:02:54Z) and once
after it (16:14:15Z). The committed `recordings/probes.json` is the second run; the
first run's two calls are included in the spend table below but their rows were
replaced in the committed file. Both rounds succeeded, so no native-format fallback
was needed (PLAN.md section 7).

| Model | Result | Input tokens | Output tokens | Latency | Cost |
| --- | --- | ---: | ---: | ---: | ---: |
| `muse-spark-1.3-contributor` | ok, valid schema | 1,291 | 1,141 | 7.7 s | USD 0.000357 |
| `gemini-4-argon` | ok, valid schema | 1,717 | 173 | 5.4 s | USD 0.005164 |

The first round found the problem that changed the request: with the gateway's
default effort, `muse-spark` spent its whole allowance on hidden reasoning and
returned empty content at 1024 tokens or cut-off JSON at 8192 tokens (1,531 output
tokens, 13.7 s in that round). With `reasoning_effort=low` it answers as above. The
client sends that parameter for this model only.

The first round also showed that the gateway reports the USD list cost under
`usage.opencode.list_cost`, not in the generic `cost` fields (which carry 0). The
cost reader now uses the gateway's USD figure, so every recorded cost is real spend.

## Smoke (20 items x 2 models)

Three smoke rounds of 20 items per model were run; only the last two left rows in
`recordings/calls.jsonl`.

1. **Exploratory smoke (2026-11-01T16:03Z, no committed rows).** 1024-token cap on
   both models and the wire schema as it was. 15 of 20 `muse-spark` answers were
   invalid (6 cut off, 8 flagged safety without the required `safety_quote`), and 4
   of 20 `gemini-4-argon` answers were invalid for the same missing quote. The cause
   was a schema bug, not a model bug: the wire schema gave every field a default, so
   the JSON schema it sent said "optional", and both models left keys out. Its calls
   were not kept, so its cost is not in the measured total; at the caps in force 40
   calls cannot have cost more than about USD 0.30.
2. **Smoke A (16:14Z, USD 0.121634).** After the schema fix: every field required,
   `muse-spark` at 2048 tokens, `gemini-4-argon` at 640. `muse-spark` had 0 invalid
   of 20; `gemini-4-argon` had 1 invalid of 20, cut off at 640 (it pretty-prints its
   JSON, so a clue-rich answer needs more room).
3. **Smoke B (16:23Z, USD 0.130192).** The production setting: `muse-spark` at 4096
   tokens, `gemini-4-argon` at 1024. Both had 0 invalid of 20. This is the setting
   the full run uses:

| Model | Invalid | Coverage | Macro-F1 | Quote grounding | Latency p50 | Cost per 1,000 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `muse-spark-1.3-contributor` | 0 | 0.90 | 0.911 | 1.000 | 12.3 s | USD 0.27 |
| `gemini-4-argon` | 0 | 0.90 | 0.911 | 1.000 | 6.0 s | USD 6.24 |

The 4096-token cap matters because `muse-spark` reasons before it answers; the
1024-token cap is the first that produced no cut-off `gemini-4-argon` answer.

## Pre-run estimate and the section 8 reduction

`estimate_cost_usd` is an upper bound: 1,000 prompt tokens and the full output
allowance per item, at the higher of peak and off-peak prices.

| Model | Items | Estimated cost |
| --- | ---: | ---: |
| `muse-spark-1.3-contributor` (4096-token cap) | 400 | USD 0.3677 |
| `gemini-4-argon` (1024-token cap) | 400 | USD 4.8960 |
| **both at 400** | 800 calls | **USD 5.2637** |

That is over the USD 3 cap, so PLAN.md section 8's reduction applies: the comparison
model runs the first 200 items (estimated USD 2.4480), which with the primary's
estimate is USD 2.8157. The guard makes the same decision on its own; it is not
hand-set. The smoke estimate for 20 items x 2 models is USD 0.0184 + USD 0.2448 =
USD 0.2632 by the same upper bound.

Why not 400 comparison items at a smaller cap: `gemini-4-argon` pretty-prints and
needs room for every required key, so 512 and 640 cut real answers off in the smoke;
1024 is the first clean cap, and its estimate leaves no room for both models at 400
items inside USD 3. A 200-item comparison with every answer valid beats 400 with a
tenth of them invalid; the summary reports the comparison at 200 items, and its
interval is wider.

## The interrupted run and the resume

The first `make live` started at 2026-11-01T16:30:06Z. The host rebooted at about
16:44Z and killed it after 69 of 400 primary cards; there was no comparison card.
The three files it was writing ended in NUL padding from the interrupted write, but
the valid prefix ended on a complete JSON line, so each was truncated back to that
line: no recorded call or card was lost. One card (item `11663876`) had outlived its
response recording in the crash; one paid call after the resume restored it.

The run resumed with one `make live` (record mode, run id `live`) from
2026-11-02T01:02:46Z to 02:14:59Z: the 69 existing cards were skipped and every
later item was called once. The primary ran all 400 items; the comparison was cut to
200 by the guard, as planned.

A second, one-call `make live` was needed for the repaired recording. After that
call the guard refused the rest of the run: the comparison model's remaining
"unscheduled" half (items 201-400) was re-estimated at USD 2.45 against USD 1.33
already spent, so it stopped instead of re-running a model that had already finished
its cut. The one card was written before that check. The failed resume left an
"incomplete" manifest, which the replay below overwrote. This is a resumability gap
in the budget guard, recorded under deviations.

## Spend against the USD 3 cap

Measured from every row in `recordings/calls.jsonl`, plus the two probe calls the
re-probe replaced. Each row's `cost_usd` is the gateway's own USD list cost.

| Stage | Calls | Primary USD | Comparison USD | Total USD |
| --- | ---: | ---: | ---: | ---: |
| probe, first round (rows replaced) | 2 | 0.000424 | 0.004192 | 0.004616 |
| probe, committed round | 2 | 0.000357 | 0.005164 | 0.005521 |
| smoke A (schema fix) | 40 | 0.005028 | 0.116606 | 0.121634 |
| smoke B (final caps) | 40 | 0.005446 | 0.124746 | 0.130192 |
| live (69 interrupted + 531 resumed + 1 repair) | 601 | 0.097797 | 1.224938 | 1.322735 |
| **total** | **685** | **0.109051** | **1.475646** | **1.584697** |

That is **USD 1.584697 of the USD 3 cap**, leaving USD 1.415303. Counting the
unrecorded exploratory smoke at its worst case (under USD 0.30) still leaves the
total under USD 1.89. No model call went outside the cap: the guard refused the one
resume that would have crossed it, and no retry ran around a policy answer.

Per-model summary: the primary cost USD 0.109051 for 400 evaluated items plus its
probe and smoke calls; the comparison cost USD 1.475646 for 200 evaluated items plus
its probe and smoke calls. The comparison is about 13.5x the primary's spend for one
fifth of the items, which is why the section 8 cut falls on it.

## Results

From `results/runs/live/metrics.json` and `results/SUMMARY.md`. Macro-F1 is the
primary metric; `unclear` counts as wrong. 95% intervals in parentheses.

| Model | Items | Macro-F1 | Accuracy | Coverage | Final safety recall / precision | Quote grounding | Cost per 1,000 | p50 / p95 |
| --- | ---: | --- | --- | --- | --- | ---: | ---: | --- |
| `muse-spark-1.3-contributor` | 400 | 0.863 (0.825-0.895) | 0.840 (0.801-0.873) | 0.880 (0.844-0.908) | 1.000 / 0.359 | 1.000 | USD 0.244 | 8.6 s / 15.3 s |
| `gemini-4-argon` | 200 | 0.851 (0.771-0.901) | 0.840 (0.783-0.884) | 0.895 (0.845-0.930) | 1.000 / 0.487 | 1.000 | USD 6.125 | 5.8 s / 11.3 s |

Both models had 0 invalid answers in the final run. The hard-rule safety decision
reaches recall 1.000 for both; the model's own flag alone also reaches 1.000 recall
but lower precision (0.374 primary, 0.569 comparison), which is why the hard rules
decide. The cost-free baselines score 0.415 macro-F1 (TF-IDF + logistic regression)
and 0.887 / 0.568 safety recall / precision (keyword rule).

The comparison ran on the first 200 items while the primary ran on all 400, so the
two columns describe overlapping but different samples; compare the intervals and
the item count before reading a gap as real. The primary leads on macro-F1 and
similar-case precision and is 25x cheaper per 1,000 items; the comparison has higher
precision on its 200-item sample and answers faster.

## Replay check

Every committed result is replay output: `make results` re-derives the cards,
metrics and summary from `recordings/` and the fixed replay clock, with no key and
no model call.

```
rm -rf results && make all      # build A
rm -rf results && make all      # build B
diff -r A B                     # no output: byte-identical
```

The same held for the section 9 sequence: `make results`, then `rm -rf results`,
then `make all` produced an identical tree (`diff -r`, no output). Both `make all`
runs ran inside `unshare -rn` with `FRT_ENV_FILE` and every key variable unset, so
the check had no key and no network. `sha256sum -c results/MANIFEST.sha256` verifies
all 10 committed hashes. The committed `results/` is the tree from that replay.

One caveat: the embedding library still tries an HF metadata HEAD when it loads,
which fails silently inside the no-network namespace and falls back to the local
cache; the replay is deterministic and offline-safe, but the attempt makes the log
noisy and adds a few seconds of retries.

## Timing

| Stage | Wall time |
| --- | --- |
| Probes (two rounds) | about 40 s of calls |
| Smokes A and B | about 10 min of calls each (40 calls) |
| Live attempt 1 | 16:30-16:44Z, 69 primary cards before the reboot |
| Live attempt 2 (resume) | 01:02:46-02:14:59Z, 531 calls, 72 min |
| Repair call | one primary call, about 15 s |
| `make all` replay | about 40 s per build (including HF retries) |

## Deviations

1. **Wire schema: every key required.** `extract/schema.py` gave each field a
   default, so the JSON schema told the models every key was optional and both left
   `safety_quote` out of true safety flags. Every field is now required, so a missing
   key is a visible invalid answer. This is a code change outside R7's owned files;
   it is the fix the smoke run forced.
2. **Reasoning effort and caps.** The client sends `reasoning_effort=low` for
   `muse-spark-1.3-contributor`, and the lock caps it at 4096 output tokens;
   `gemini-4-argon` is capped at 1024. Without those, the smoke answers were empty or
   cut off.
3. **Section 8 cut.** The comparison model ran the first 200 of 400 items because
   the upper-bound estimate at 400 items (USD 4.90) breaks the cap. The cut is in
   `metrics.json` (`reduced: true`, `items_run: 200`).
4. **Interrupted run.** The host rebooted mid-run; NUL padding was truncated from
   three files to the last complete line, and one missing response recording was
   restored with one paid call. No card or call row was fabricated.
5. **Budget accounting by key.** The runner sums the calls sidecar keyed by
   (model, item), so a second paid call for the same item (a smoke call the live run
   repeats) counts once in its guard. The spend table above sums every raw row; it is
   the figure checked against the cap, and it is USD 1.58, far below the guard's own
   view.
6. **Resume after a reduced run.** A completed run whose comparison model was cut
   cannot be resumed for one missing primary card: the guard estimates the remaining
   half of the comparison set again and stops. The one repair call was made before
   that check and the replay completed the run. A future fix would persist the cut
   in the run state instead of re-deriving it from the cards on disk.
7. **First probe replaced.** The committed `recordings/probes.json` holds the second
   probe round; the first round's two call rows were replaced when the probe was
   re-run. Both rounds are in the spend table.
8. **Pacing.** Calls were issued sequentially, which is within the "at most 2
   concurrent" limit; the 30/minute window never bound. Observed throughput was about
   5 items per minute.
9. **No native-endpoint fallback.** Both models answered on the OpenAI-compatible
   endpoint, so plan section 7's fallback path was not used.

# Lane interfaces

This file is the integration contract between lanes. `contracts.py` holds the shared
**types**; this file holds the shared **functions** and the rules for who may import
what. A lane may add private helpers freely; changing a name or signature below is a
cross-lane change and needs the captain.

Owners are the task ids in `plan/TASKS.md`. R0 owns this file; later lanes read it and
implement their block. The versions `e1`, `rb1` and `hr1` are frozen by `PLAN.md` §4.

## 0. Import rules

```
contracts  <-  data
           <-  llm      <-  extract
           <-  similar
           <-  rules
           <-  trend
           <-  pipeline / report        (may import every lane above)
```

- `field_return_triage.contracts` imports nothing from this project. R0 owns it; it is
  frozen after Wave 0. No lane edits it.
- `data`, `llm`, `extract`, `similar`, `rules` and `trend` may import `contracts`, the
  standard library and their own third-party libraries. They must not import each other,
  except `extract` which may import `llm`. That is what lets R1–R5 run in parallel.
- `pipeline` and `report` are the only packages that may import every lane.
- Only `llm/` may read a credential, and only from the process environment, then the file
  named by `FRT_ENV_FILE`, then `.env`. The value never enters a contract, log, trace,
  recording or error message.
- Tests never open an INET socket. `tests/conftest.py` enforces it with `pytest-socket`,
  allowing unix sockets only.
- A lane builds fakes in `tests/fixtures/<lane>/` and commits them. Recordings used by
  tests live in `tests/fixtures/recordings/` (R6).

## 1. Owner map and command dispatch

| Lane | Owns | Public entry points |
| --- | --- | --- |
| R1 data | `src/field_return_triage/data/`, `scripts/fetch_nhtsa.py`, `data/`, `tests/data/` | `data.*`, `make fetch-data/data` |
| R2 llm + extract | `src/field_return_triage/llm/`, `src/field_return_triage/extract/`, `config/prices.toml`, `config/budget.toml`, `tests/llm/`, `tests/extract/` | `llm.*`, `extract.*` |
| R3 similar | `src/field_return_triage/similar/`, `tests/similar/` | `similar.*`, `make index` |
| R4 rules | `src/field_return_triage/rules/`, `config/rulebook.toml`, `tests/rules/` | `rules.*`, `frt review` |
| R5 trend | `src/field_return_triage/trend/`, `tests/trend/` | `trend.*`, `make trend` |
| R6 pipeline | `src/field_return_triage/pipeline/`, CLI wiring, `tests/pipeline/`, `tests/fixtures/recordings/` | `pipeline.*`, `frt triage`, `frt eval`, `make all/results/eval-replay` |
| R8 report | `src/field_return_triage/report/`, `web/`, `dist/`, `results/page/` | `report.*`, `make page-data/page` |

`src/field_return_triage/cli.py` is owned by R0 and is never edited by a lane. Each
command dispatches to a lane module; a lane replaces its stub by adding that module with
that named function:

| Command | Module | Entry function | Lane |
| --- | --- | --- | --- |
| `frt data` | `field_return_triage.data.cli` | `data_main() -> None` | R1 |
| `frt index` | `field_return_triage.similar.cli` | `index_main() -> None` | R3 |
| `frt triage FILE\|-` | `field_return_triage.pipeline.cli` | `triage_main(source: str) -> None` | R6 |
| `frt eval --mode replay\|record` | `field_return_triage.pipeline.cli` | `eval_main(mode: str) -> None` | R6 |
| `frt review` | `field_return_triage.rules.cli` | `review_main() -> None` | R4 |
| `frt trend` | `field_return_triage.trend.cli` | `trend_main() -> None` | R5 |

A lane that owns a Makefile stub replaces only that target's recipe and adds its own
dependencies; it does not rename targets. Baselines use the same convention:
`data_main()` also runs `make data` when called from the CLI.

A lane may print to the terminal from its `cli.py`; library modules never print. The
`T201` Ruff exemption exists only for the CLI modules and scripts.

## 2. Contracts (R0, frozen)

From `field_return_triage.contracts`:

- `Complaint` — id, narrative, received date, make/model/model_year, raw `component`,
  mapped `group`, and the coded `crash`/`fire`/`injury` flags. `coded_safety` is their OR.
- `Clue` — `kind` + `quote`. `SymptomKind` and `ConditionKind` are the fixed vocabularies.
- `Extraction` — `component_group`, `safety_relevant` + `safety_quote`, `symptoms`,
  `conditions`, `fault_codes`, `mileage`. A safety flag without its quote is invalid.
- `QuoteCheck` — `checked`, `passed`, `dropped` (`DroppedClue` rows), plus `all_passed`
  and `none_passed`. `checked == passed + len(dropped)` is enforced.
- `Neighbour` — complaint id, group, received date, safety flag, ≤200-character excerpt,
  cosine score in [-1, 1].
- `Suggestion` — at least one test, what to inspect, what information to request, and
  `Reason`s that point at their quotes.
- `TriageCard` — the frozen card: complaint, extraction, quote check, priority, human
  review flag, reasons, quotes, neighbours, suggestion, model and versions, timestamp.
  It has no closure, scrap or return field, by design.
- `Decision` — one technician feedback row: card id, complaint id, `accept|change`,
  optional reason (required for `change`), aware timestamp, optional time to decision.
- `TrendAlert` — series, Monday week start, count ≥ 3, floored trailing mean, threshold.
- `SeriesKey`, `WeeklyCount`, `Recall` — trend support types.
- `ModelSetting`, `RunManifest` — model settings, prompt/rulebook/hard-rule versions,
  sha256 sample hash, mode and cost.

All contracts are frozen, reject unknown fields, and require timezone-aware datetimes.
Use `datetime.now(UTC)` or pass a clock for tests. A week always starts on Monday.

## 3. R1 — `field_return_triage.data`

```python
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

from field_return_triage.contracts import Complaint, Recall, WeeklyCount


def load_groups(path: Path = Path("data/groups.toml")) -> dict[str, tuple[str, ...]]:
    """group id -> raw component labels; copied byte for byte from the spec."""


def map_component(component: str, groups: dict[str, tuple[str, ...]]) -> str | None:
    """The single group for a raw label, or None for unmapped/multi-group."""


def pii_reason(narrative: str) -> str | None:
    """Why the narrative must be dropped, or None when it is clean (PLAN §5)."""


def derive_library(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
    *,
    seed: int = 20261031,
    limit: int = 20_000,
) -> list[Complaint]: ...


def derive_eval(
    rows: Iterable[dict[str, Any]],
    groups: dict[str, tuple[str, ...]],
    *,
    seed: int = 20261031,
    size: int = 400,
) -> list[Complaint]: ...


def derive_weekly(rows: Iterable[dict[str, Any]]) -> list[WeeklyCount]: ...
def derive_recalls(rows: Iterable[dict[str, Any]]) -> list[Recall]: ...


def write_library(items: Sequence[Complaint], path: Path) -> str:
    """Write gzipped JSONL; return the sha256 of the written bytes."""


def write_eval(items: Sequence[Complaint], path: Path) -> str: ...
def write_weekly(items: Sequence[WeeklyCount], path: Path) -> str: ...
def write_recalls(items: Sequence[Recall], path: Path) -> None: ...


def load_library(path: Path = Path("data/library.jsonl.gz")) -> list[Complaint]: ...
def load_eval(path: Path = Path("data/eval.jsonl")) -> list[Complaint]: ...
def load_weekly(path: Path = Path("data/trend/weekly.csv.gz")) -> list[WeeklyCount]: ...
def load_recalls(path: Path = Path("data/trend/recalls.csv")) -> list[Recall]: ...
```

`data_main()` runs fetch (snapshot first), derive, write, then `data/CHECKSUMS.txt` and
`data/STATS.md`. JSONL rows are one contract per line, keys sorted, UTF-8, `\n` endings.
`load_*` accepts the path argument so tests and R6 use fixtures without touching the
committed data. Committed derived files are the source of truth (PLAN §5).

## 4. R2 — `field_return_triage.llm` and `.extract`

```python
# llm/client.py
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from pydantic import BaseModel

from field_return_triage.contracts import ModelSetting, RunMode


class Message(Protocol):
    """Any object with role/content works; dicts {"role": ..., "content": ...} are the base."""


class ModelReply(BaseModel):
    content: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    model_id: str
    prompt_version: str


def load_model_settings(
    path: Path = Path("config/models.lock.toml"),
) -> tuple[ModelSetting, ...]: ...


class ChatClient:
    def __init__(
        self,
        settings: ModelSetting,
        *,
        mode: RunMode = RunMode.REPLAY,
        recordings: Path = Path("recordings"),
        budget_path: Path = Path("config/budget.toml"),
        transport: Any | None = None,  # fake httpx transport in tests
    ) -> None: ...

    def complete(
        self,
        messages: Sequence[Mapping[str, str]],
        *,
        schema: type[BaseModel] | None = None,
    ) -> ModelReply:
        """One call, or one replay hit. Never touches the network in replay mode."""


# llm/record.py
def recording_key(model_id: str, prompt_version: str, messages: Sequence[Mapping[str, str]]) -> str:
    """sha256(model id \\n prompt version \\n sha256(canonical JSON of messages))."""


class Recorder:
    def record(self, key: str, reply: ModelReply) -> None: ...
    def lookup(self, key: str) -> ModelReply | None: ...


# llm/cost.py
def estimate_cost_usd(settings: ModelSetting, items: int, prices_path: Path) -> float: ...


# extract/prompt.py
PROMPT_VERSION: str = "e1"


def build_messages(complaint: Complaint, groups: Mapping[str, str]) -> list[dict[str, str]]: ...


# extract/parse.py
def parse_extraction(raw: str) -> tuple[Extraction | None, str | None]:
    """(extraction, None) or (None, reason). Never retries an invalid answer."""


# extract/quotecheck.py
def normalise(text: str) -> str:
    """Whitespace-normalised, case-folded text used by the quote check."""


def quote_passes(quote: str, narrative: str) -> bool: ...
def check_quotes(extraction: Extraction, narrative: str) -> QuoteCheck: ...


# extract/run.py
def extract(
    complaint: Complaint,
    client: ChatClient,
    groups: Mapping[str, str],
) -> tuple[Extraction | None, QuoteCheck, str | None]:
    """(extraction, quote check, failure reason)."""
```

The client reads credentials only through `FRT_ENV_FILE` or `.env`, and only in record
mode. A 403 or an abuse/policy message stops every call and writes `reports/STOP.md`
(PLAN §10.5). Replay misses raise; they never fall back to the network.

## 5. R3 — `field_return_triage.similar`

```python
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

import numpy as np
from numpy.typing import NDArray

from field_return_triage.contracts import Complaint, Neighbour

EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
EXCERPT_CHARS: int = 200


class Embedder(Protocol):
    def encode(self, texts: Sequence[str], *, batch_size: int = 64) -> NDArray[np.float32]: ...


def default_embedder(*, allow_download: bool = False) -> Embedder:
    """The CPU sentence-transformers model; offline by default, and `make index` is the
    only caller that passes `allow_download=True` for the one-time download."""


def cache_dir() -> Path:
    """~/.cache/field-return-triage/, keyed by data/CHECKSUMS.txt."""


def build_index(
    library: Sequence[Complaint],
    *,
    embedder: Embedder | None = None,
    checksums: Path = Path("data/CHECKSUMS.txt"),
) -> Path:
    """Embed and persist (ids, vectors); return the cache path."""


def load_index(path: Path | None = None) -> tuple[list[str], NDArray[np.float32]]: ...


def search(
    query_text: str,
    index: tuple[list[str], NDArray[np.float32]],
    library: Sequence[Complaint],
    *,
    k: int = 5,
    embedder: Embedder | None = None,
) -> list[Neighbour]: ...


def nearest(
    complaint: Complaint,
    library: Sequence[Complaint],
    *,
    k: int = 5,
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
) -> list[Neighbour]: ...


def precision_at_k(
    queries: Sequence[Complaint],
    library: Sequence[Complaint],
    *,
    k: int = 5,
    index: ... = None,
    embedder: Embedder | None = None,
) -> float: ...
```

Scores are cosine similarities rounded to 4 decimals before ranking; ties break by
complaint id ascending. The excerpt is the first 200 characters of the narrative after
whitespace normalisation. `index_main()` calls `build_index` on `data/library.jsonl.gz`.

## 6. R4 — `field_return_triage.rules`

```python
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from field_return_triage.contracts import (
    Complaint,
    Decision,
    Extraction,
    Neighbour,
    Priority,
    QuoteCheck,
    Suggestion,
    TriageCard,
)


# rules/rulebook.py
RULEBOOK_PATH: Path = Path("config/rulebook.toml")
RULEBOOK_VERSION: str = "rb1"


class Rulebook:
    version: str
    by_kind: Mapping[str, "Rule"]
    fallback_test: str
    fallback_inspect: tuple[str, ...]
    fallback_request: tuple[str, ...]


def load_rulebook(path: Path = RULEBOOK_PATH) -> Rulebook: ...


# rules/keywords.py
def load_safety_keywords(path: Path = Path("data/safety_keywords.txt")) -> tuple[str, ...]: ...
def keyword_safety(narrative: str, keywords: Sequence[str]) -> str | None:
    """The first narrative span that matched a keyword, or None."""


# rules/hard_rules.py
HARD_RULE_VERSION: str = "hr1"


def decides_safety(
    complaint: Complaint,
    extraction: Extraction,
    keyword_quote: str | None,
) -> tuple[bool, tuple[str, ...]]:
    """(safety, the reasons that made it so), in a fixed order."""


def route(
    complaint: Complaint,
    extraction: Extraction,
    quote_check: QuoteCheck,
    *,
    safety: bool,
) -> tuple[Priority, bool]:
    """(priority, needs_human_review) per PLAN §4 hard rules."""


def suggest(
    extraction: Extraction,
    quote_check: QuoteCheck,
    rulebook: Rulebook,
) -> Suggestion: ...


def build_card(
    complaint: Complaint,
    extraction: Extraction,
    quote_check: QuoteCheck,
    *,
    neighbours: Sequence[Neighbour],
    rulebook: Rulebook,
    model_id: str,
    keywords: Sequence[str],
    now: datetime | None = None,
) -> TriageCard: ...


# rules/feedback.py
DECISIONS_PATH: Path = Path("data/feedback/decisions.jsonl")


def append_decision(decision: Decision, path: Path = DECISIONS_PATH) -> None: ...
def load_decisions(path: Path = DECISIONS_PATH) -> list[Decision]: ...


# rules/kpi.py
def acceptance_rate(decisions: Sequence[Decision]) -> float | None: ...
def change_reasons(decisions: Sequence[Decision]) -> Mapping[str, int]: ...
def median_time_to_decision_s(decisions: Sequence[Decision]) -> float | None: ...
```

Safety wins over every other rule and can never be demoted: `route` returns priority 1
and `needs_human_review=True` whenever `safety` is true or the coded fields are set. With
`component_group == "unclear"` or no passing quote, the card goes to priority 3 and human
reading. The rulebook is an example to adapt to a lab's test catalogue, and says so in a
comment. `review_main()` shows one card and appends one `Decision` line.

## 7. R5 — `field_return_triage.trend`

```python
from collections.abc import Sequence
from datetime import date
from pathlib import Path

from field_return_triage.contracts import Recall, SeriesKey, TrendAlert, WeeklyCount

TRAILING_WEEKS: int = 26
MIN_COUNT: int = 3
CONFIDENCE: float = 0.999
MEAN_FLOOR: float = 0.5
MAX_LEAD_DAYS: int = 365
ALERTS_PATH: Path = Path("results/trend/alerts.json")
BACKTEST_PATH: Path = Path("results/trend/backtest.json")
SERIES_PATH: Path = Path("results/trend/example_series.json")


def series(rows: Sequence[WeeklyCount]) -> dict[SeriesKey, list[WeeklyCount]]:
    """Group rows by series, each list sorted by week."""


def poisson_upper(mean: float, *, confidence: float = CONFIDENCE) -> float:
    """The Poisson upper limit used by the alert rule."""


def detect_alerts(
    rows: Sequence[WeeklyCount],
    *,
    weeks: int = TRAILING_WEEKS,
    min_count: int = MIN_COUNT,
) -> list[TrendAlert]: ...


def precedes_recall(alert: TrendAlert, recalls: Sequence[Recall], *, max_days: int = MAX_LEAD_DAYS) -> Recall | None: ...


def base_rate(
    alerts: Sequence[TrendAlert],
    rows: Sequence[WeeklyCount],
    recalls: Sequence[Recall],
    *,
    seed: int = 20261031,
) -> dict[str, float]:
    """Share of random same-series weeks that precede a recall, with a 95% CI."""


def backtest(alerts: Sequence[TrendAlert], rows: Sequence[WeeklyCount], recalls: Sequence[Recall], *, seed: int = 20261031) -> dict[str, object]: ...


def example_series(alerts: Sequence[TrendAlert], rows: Sequence[WeeklyCount], recalls: Sequence[Recall]) -> dict[str, object]: ...


def write_outputs(...) -> None: ...
```

`trend_main()` writes the three files under `results/trend/`. The backtest always reports
the base rate beside the raw share; the raw share alone is never the headline. The
example series is the alert with the longest lead time among series with at least 20
complaints. If fewer than 20 alerts join a recall, the file says so plainly.

## 8. R6 — `field_return_triage.pipeline`

```python
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from field_return_triage.contracts import Complaint, RunManifest, TriageCard


# pipeline/triage.py
def triage_one(
    complaint: Complaint,
    *,
    client: ChatClient,
    library: Sequence[Complaint],
    rulebook: Rulebook,
    groups: Mapping[str, str],
    keywords: Sequence[str],
    index: tuple[list[str], NDArray[np.float32]] | None = None,
    embedder: Embedder | None = None,
    now: datetime | None = None,
) -> TriageCard: ...


def triage_text(text: str, *, complaint_id: str = "cli", ...) -> TriageCard: ...


# pipeline/run.py
def run_eval(
    *,
    mode: RunMode,
    models_path: Path = Path("config/models.lock.toml"),
    run_id: str,
    items_path: Path = Path("data/eval.jsonl"),
    out_dir: Path = Path("results/runs"),
    budget_path: Path = Path("config/budget.toml"),
    limit: int | None = None,
) -> RunManifest:
    """Resumable. Replay needs no key and no network; record applies the PLAN §8 budget."""


# pipeline/metrics.py
class Metric(BaseModel):
    value: float | None = None  # None when the denominator is zero
    ci_low: float | None = None
    ci_high: float | None = None


def macro_f1(gold: Sequence[str], predicted: Sequence[str]) -> Metric: ...
def bootstrap_ci(values: Sequence[float], *, resamples: int = 2_000, seed: int = 20261031) -> tuple[float, float]: ...
def safety_scores(cards: Sequence[TriageCard], items: Sequence[Complaint]) -> dict[str, Metric]: ...
def quote_grounding(cards: Sequence[TriageCard]) -> Metric: ...
def condition_agreement(cards: Sequence[TriageCard], keywords: ...) -> Metric: ...
def routing(cards: Sequence[TriageCard]) -> dict[str, Metric]: ...
def latency_ms(durations: Sequence[float]) -> dict[str, Metric]: ...


# pipeline/baseline.py
def run_baselines(items: Sequence[Complaint], library: Sequence[Complaint]) -> dict[str, object]: ...
```

`triage_main` reads a file or stdin and prints JSON plus a readable text view.
`eval_main` maps `--mode` to `RunMode`, requires `FRT_ENV_FILE` or `.env` only in record
mode, and writes `results/runs/<id>/{manifest.json,cards.jsonl,metrics.json,schedule.json}`.
The schedule records how many items each model was planned to run, so a resumed run
honours the PLAN section 8 cut instead of re-estimating items the cut removed. R6 adds
`--models FILE` and `--run-id ID` to the `frt eval` command, plus these keyword-only
`run_eval` parameters with defaults: `library_path`, `groups_path`, `recordings_path`,
`prices_path`, `checksums_path`, `index`, `embedder`, `clock`, `wall_clock` and
`client_factory` (tests inject them; production passes none).

Record mode appends one row per call to `<recordings>/calls.jsonl` with the run id, cost
and duration; replay reads that sidecar so a reduced run is reproduced exactly and the
frozen recordings still hold content and usage only. `triage_item` is the shared
implementation and also returns the call's usage/cost/duration; `triage_one` keeps the
signature above. Before `config/models.lock.toml` exists, the pipeline runs in fixture
mode on `tests/fixtures/recordings/` and says so on every command line and in
`results/SUMMARY.md`.

`make all` = data check → index (cached) → trend → results (replay) → page-data → page,
and is byte-identical twice. Until R8 lands the report package, `make all` stops after
`results` with a one-line note; it runs the page targets automatically as soon as
`src/field_return_triage/report/` exists.

## 9. R8 — `field_return_triage.report`

```python
from pathlib import Path
from typing import Any

RESULTS: Path = Path("results")
PAGE_DATA: Path = Path("results/page/page-data.json")
DIST: Path = Path("dist/field-return-triage/index.html")


def build_summary(runs_dir: Path = RESULTS / "runs") -> str: ...
def write_manifest(results_dir: Path = RESULTS) -> Path:
    """results/MANIFEST.sha256 over every committed results file, sorted."""


def build_page_data(results_dir: Path = RESULTS) -> dict[str, Any]: ...
def build_page(data_path: Path = PAGE_DATA, out: Path = DIST) -> Path: ...


def main() -> None: ...
```

Every number on the page comes from a committed file under `results/`. The page is
static, works offline except the GitHub link, and is checked at 360 px in light and dark.

## 10. Cross-lane rules that make parallel work merge cleanly

1. **Time.** Pass `now` into anything that needs a clock; default to
   `datetime.now(UTC)` inside the function. Tests use a fixed clock.
2. **Determinism.** Seeds are `20261031` unless `PLAN.md` says otherwise. Sort before
   sampling; ties break on id. Round similarity to 4 decimals before ranking and metrics
   to the precision the page shows.
3. **No printing from libraries.** `typer.echo` belongs in `*/cli.py` only.
4. **Fakes over mocks of our own code.** Tests inject `Embedder`, `transport` or
   `ChatClient` fakes; they never patch `contracts` or skip the quote check.
5. **Fixtures are committed and tiny.** A fixture that needs the network is not a
   fixture. Tests run with sockets blocked.
6. **Makefile stubs** print `not built yet (lane Rn)` and exit 1; replace only your own
   target, keep the target name and help text.
7. **Lane reports** go in `reports/lanes/<ID>.md`; deviations go there and in
   `reports/DEVIATIONS.md` when the captain needs to see them.

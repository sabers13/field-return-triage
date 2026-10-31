"""Shared pydantic v2 contracts for field-return-triage.

These models are the interface between lanes. The shape is frozen after R0 (Wave 0):
later lanes may add fields only through a captain-approved change, because results,
recordings and the page all depend on them.

Two rules the types make structural:

* every extracted clue carries the exact words it came from, so a claim can always be
  traced back to the complaint text;
* no card, decision or manifest field can mark a case closed, scrapped or returned.
  The technician decides; the AI only suggests.

No field may hold a secret. ``RunManifest`` records model settings, never credentials.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import IntEnum, StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "HARD_RULE_VERSION",
    "PROMPT_VERSION",
    "RULEBOOK_VERSION",
    "SCHEMA_VERSION",
    "UNCLEAR_GROUP",
    "Clue",
    "Complaint",
    "ConditionKind",
    "Decision",
    "DecisionAction",
    "DroppedClue",
    "Extraction",
    "FaultCode",
    "Mileage",
    "ModelSetting",
    "Neighbour",
    "Priority",
    "QuoteCheck",
    "Reason",
    "Recall",
    "RunManifest",
    "RunMode",
    "SeriesKey",
    "Suggestion",
    "SymptomKind",
    "TrendAlert",
    "TriageCard",
    "WeeklyCount",
]

#: Bumped only when a contract changes shape. Recorded in every run manifest.
SCHEMA_VERSION = "1.0.0"

#: Versions fixed by ``PLAN.md`` §4.
PROMPT_VERSION = "e1"
RULEBOOK_VERSION = "rb1"
HARD_RULE_VERSION = "hr1"

#: ``component_group`` value used when the complaint names no single group (PLAN §4).
UNCLEAR_GROUP = "unclear"

_GROUP_PATTERN = r"^[a-z][a-z0-9_]*$"


class _Contract(BaseModel):
    """Base for every contract: immutable, closed to unknown fields."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_aware(value: datetime, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field} must be timezone-aware (UTC)"
        raise ValueError(msg)
    return value


def _require_monday(value: date) -> date:
    if value.weekday() != 0:
        msg = "week must be the Monday that starts the week"
        raise ValueError(msg)
    return value


class SymptomKind(StrEnum):
    """Fixed symptom vocabulary from ``PLAN.md`` §4. Never invent a new value."""

    NO_FUNCTION = "no_function"
    INTERMITTENT = "intermittent"
    WARNING_LIGHT = "warning_light"
    SMOKE_OR_BURN = "smoke_or_burn"
    NOISE = "noise"
    DISPLAY_FAULT = "display_fault"
    BATTERY_DRAIN = "battery_drain"
    OTHER = "other"


class ConditionKind(StrEnum):
    """Fixed condition vocabulary from ``PLAN.md`` §4. Never invent a new value."""

    MOISTURE = "moisture"
    COLD = "cold"
    HEAT = "heat"
    VIBRATION_OR_ROAD = "vibration_or_road"
    AFTER_SERVICE = "after_service"
    CHARGING = "charging"
    SPEED_OR_LOAD = "speed_or_load"
    STARTUP = "startup"
    OTHER = "other"


class Priority(IntEnum):
    """Card ordering. Safety is always 1; nothing may demote it."""

    SAFETY = 1
    CLEAR_CLUES = 2
    HUMAN_READING = 3


class DecisionAction(StrEnum):
    """What a technician did with a card. There is no close/scrap/return action."""

    ACCEPT = "accept"
    CHANGE = "change"


class RunMode(StrEnum):
    """Replay never touches the network; record is only used by the paid lane."""

    REPLAY = "replay"
    RECORD = "record"


class Complaint(_Contract):
    """One complaint as committed in the derived data.

    Location and identity columns are dropped before this model is built (PLAN §5).
    ``group`` is the mapped single group, or ``None`` when the complaint is unmapped.
    """

    id: str = Field(min_length=1)
    narrative: str = Field(min_length=1)
    received: date
    make: str | None = None
    model: str | None = None
    model_year: int | None = Field(default=None, ge=1900, le=2100)
    component: str | None = Field(default=None, description="raw coded component label")
    group: str | None = Field(default=None, pattern=_GROUP_PATTERN)
    crash: bool = False
    fire: bool = False
    injury: bool = False

    @property
    def coded_safety(self) -> bool:
        """True when the coded crash/fire/injury fields flag the complaint."""
        return self.crash or self.fire or self.injury


class Clue(_Contract):
    """A symptom or condition, with the exact words it came from.

    ``kind`` is one of :class:`SymptomKind` or :class:`ConditionKind`; the owning
    :class:`Extraction` field decides which vocabulary applies.
    """

    kind: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class FaultCode(_Contract):
    """A fault code mentioned in the narrative, with the words it came from."""

    code: str = Field(min_length=1)
    quote: str = Field(min_length=1)


class Mileage(_Contract):
    """An odometer reading, with the words it came from."""

    value: int = Field(ge=0)
    quote: str = Field(min_length=1)


class Extraction(_Contract):
    """The model's structured reading of one complaint (``PLAN.md`` §4, prompt e1)."""

    component_group: str = Field(default=UNCLEAR_GROUP, pattern=_GROUP_PATTERN)
    safety_relevant: bool = False
    safety_quote: str | None = None
    symptoms: tuple[Clue, ...] = ()
    conditions: tuple[Clue, ...] = ()
    fault_codes: tuple[FaultCode, ...] = ()
    mileage: Mileage | None = None

    @field_validator("symptoms")
    @classmethod
    def _symptom_kinds(cls, value: tuple[Clue, ...]) -> tuple[Clue, ...]:
        allowed = {kind.value for kind in SymptomKind}
        for clue in value:
            if clue.kind not in allowed:
                msg = f"symptom kind must be one of {sorted(allowed)}, got {clue.kind!r}"
                raise ValueError(msg)
        return value

    @field_validator("conditions")
    @classmethod
    def _condition_kinds(cls, value: tuple[Clue, ...]) -> tuple[Clue, ...]:
        allowed = {kind.value for kind in ConditionKind}
        for clue in value:
            if clue.kind not in allowed:
                msg = f"condition kind must be one of {sorted(allowed)}, got {clue.kind!r}"
                raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _safety_quote_follows_the_flag(self) -> Extraction:
        if self.safety_relevant and not self.safety_quote:
            msg = "safety_relevant=True requires the safety_quote it came from"
            raise ValueError(msg)
        if not self.safety_relevant and self.safety_quote is not None:
            msg = "safety_quote must be null when safety_relevant is False"
            raise ValueError(msg)
        return self


class DroppedClue(_Contract):
    """A clue that failed the quote check, kept so the drop can be counted."""

    field: Literal["safety", "symptoms", "conditions", "fault_codes", "mileage"]
    kind: str = Field(min_length=1)
    quote: str = Field(min_length=1)
    reason: str = Field(default="not verbatim in the narrative", min_length=1)


class QuoteCheck(_Contract):
    """The result of checking every extracted quote against the narrative (PLAN §4)."""

    checked: int = Field(ge=0)
    passed: int = Field(ge=0)
    dropped: tuple[DroppedClue, ...] = ()

    @model_validator(mode="after")
    def _counts_add_up(self) -> QuoteCheck:
        if self.checked != self.passed + len(self.dropped):
            msg = (
                "checked must equal passed + len(dropped): "
                f"{self.checked} != {self.passed} + {len(self.dropped)}"
            )
            raise ValueError(msg)
        return self

    @property
    def all_passed(self) -> bool:
        """True when at least one quote was checked and none was dropped."""
        return self.checked > 0 and self.passed == self.checked

    @property
    def none_passed(self) -> bool:
        """True when the extractor produced quotes but every one failed the check."""
        return self.checked > 0 and self.passed == 0


class Neighbour(_Contract):
    """One similar past complaint (PLAN §4 step 4)."""

    complaint_id: str = Field(min_length=1)
    group: str = Field(pattern=_GROUP_PATTERN)
    received: date
    safety_relevant: bool
    excerpt: str = Field(min_length=1, max_length=200)
    score: float = Field(ge=-1.0, le=1.0)


class Reason(_Contract):
    """Why a suggestion or a routing decision was made, pointing at its quotes."""

    text: str = Field(min_length=1)
    quotes: tuple[str, ...] = ()


class Suggestion(_Contract):
    """The next test(s) the rulebook proposes, with reasons and missing information."""

    tests: tuple[str, ...] = Field(min_length=1)
    inspect: tuple[str, ...] = ()
    request: tuple[str, ...] = ()
    reasons: tuple[Reason, ...] = ()


class TriageCard(_Contract):
    """One technician-facing card. It carries no closure state by design."""

    card_id: str = Field(min_length=1)
    complaint: Complaint
    extraction: Extraction
    quote_check: QuoteCheck
    priority: Priority
    needs_human_review: bool
    reasons: tuple[Reason, ...]
    quotes: tuple[str, ...] = ()
    neighbours: tuple[Neighbour, ...] = ()
    suggestion: Suggestion
    model_id: str = Field(min_length=1)
    prompt_version: str = PROMPT_VERSION
    rulebook_version: str = RULEBOOK_VERSION
    hard_rule_version: str = HARD_RULE_VERSION
    created_at: datetime
    schema_version: str = SCHEMA_VERSION

    @field_validator("created_at")
    @classmethod
    def _created_at_is_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "created_at")


class Decision(_Contract):
    """A technician's feedback on one card, appended to the JSONL log (PLAN §4)."""

    card_id: str = Field(min_length=1)
    complaint_id: str = Field(min_length=1)
    action: DecisionAction
    reason: str | None = None
    decided_at: datetime
    time_to_decision_s: float | None = Field(default=None, ge=0)

    @field_validator("decided_at")
    @classmethod
    def _decided_at_is_aware(cls, value: datetime) -> datetime:
        return _require_aware(value, "decided_at")

    @model_validator(mode="after")
    def _change_needs_a_reason(self) -> Decision:
        if self.action is DecisionAction.CHANGE and not (self.reason or "").strip():
            msg = "a change decision requires the technician's reason"
            raise ValueError(msg)
        return self


class SeriesKey(_Contract):
    """The trend series identity fixed by ``PLAN.md`` §6."""

    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_year: int = Field(ge=1900, le=2100)
    group: str = Field(pattern=_GROUP_PATTERN)


class WeeklyCount(_Contract):
    """One week of complaint counts for one series. Counts only, no text."""

    series: SeriesKey
    week: date
    count: int = Field(ge=0)

    @field_validator("week")
    @classmethod
    def _week_starts_on_monday(cls, value: date) -> date:
        return _require_monday(value)


class TrendAlert(_Contract):
    """A weekly count that cleared the Poisson spike rule (``PLAN.md`` §6)."""

    series: SeriesKey
    week: date
    count: int = Field(ge=3)
    trailing_mean: float = Field(ge=0.5, description="trailing 26-week mean, floored at 0.5")
    threshold: float = Field(ge=0, description="Poisson 99.9% upper limit for trailing_mean")

    @field_validator("week")
    @classmethod
    def _week_starts_on_monday(cls, value: date) -> date:
        return _require_monday(value)


class Recall(_Contract):
    """One recall mapped to a component group, for the trend backtest (PLAN §5)."""

    recall_id: str = Field(min_length=1)
    make: str = Field(min_length=1)
    model: str = Field(min_length=1)
    model_year: int = Field(ge=1900, le=2100)
    group: str = Field(pattern=_GROUP_PATTERN)
    report_date: date


class ModelSetting(_Contract):
    """How one model is called. ``base_url`` is the gateway root, not a credential."""

    role: Literal["primary", "comparison"]
    model_id: str = Field(min_length=1)
    provider: str = Field(default="opencode-go", min_length=1)
    base_url: str = "https://opencode.ai/inference/go/openai/v1"
    temperature: float = Field(default=0.0, ge=0.0, le=2.0)
    max_output_tokens: int = Field(default=1024, ge=1)

    @field_validator("base_url")
    @classmethod
    def _base_url_is_http(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            msg = "base_url must start with http:// or https://"
            raise ValueError(msg)
        if "@" in value.split("://", 1)[1].split("/", 1)[0]:
            msg = "base_url must not carry credentials in the URL"
            raise ValueError(msg)
        return value


class RunManifest(_Contract):
    """What a run was: models and settings, versions, sample hash, cost (PLAN §9)."""

    run_id: str = Field(min_length=1)
    mode: RunMode
    models: tuple[ModelSetting, ...] = Field(min_length=1)
    prompt_version: str = PROMPT_VERSION
    rulebook_version: str = RULEBOOK_VERSION
    hard_rule_version: str = HARD_RULE_VERSION
    sample_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    item_count: int = Field(ge=0)
    started_at: datetime
    finished_at: datetime | None = None
    cost_usd: float | None = Field(default=None, ge=0)
    schema_version: str = SCHEMA_VERSION

    @field_validator("started_at", "finished_at")
    @classmethod
    def _timestamps_are_aware(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        return _require_aware(value, "timestamp")

    @model_validator(mode="after")
    def _finish_follows_start(self) -> RunManifest:
        if self.finished_at is not None and self.finished_at < self.started_at:
            msg = "finished_at must not be before started_at"
            raise ValueError(msg)
        return self

"""Record and replay model answers (PLAN §9).

A recording row holds the lookup key, the content and the usage only - no headers, no
request, no credential. The key is::

    sha256(model id + "\\n" + prompt version + "\\n" + sha256(canonical JSON of messages))

One JSONL file per model id is written under the recordings directory. Replay never
touches the network: a miss raises :class:`ReplayMissError`.
"""

from __future__ import annotations

import hashlib
import json
import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from field_return_triage.llm.errors import ConfigurationError
from field_return_triage.llm.reply import ModelReply

__all__ = ["Recorder", "canonical_messages", "recording_key", "recording_path"]


def canonical_messages(messages: Sequence[Mapping[str, str]]) -> str:
    """Canonical JSON of the role/content pairs, in order."""
    pairs = [{"role": message["role"], "content": message["content"]} for message in messages]
    return json.dumps(pairs, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def recording_key(
    model_id: str,
    prompt_version: str,
    messages: Sequence[Mapping[str, str]],
) -> str:
    """The recording key fixed by the R2 brief and PLAN §9."""
    digest = hashlib.sha256(canonical_messages(messages).encode("utf-8")).hexdigest()
    material = f"{model_id}\n{prompt_version}\n{digest}".encode()
    return hashlib.sha256(material).hexdigest()


def recording_path(recordings: Path, model_id: str) -> Path:
    """One file per model, with a filesystem-safe name."""
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in model_id)
    return recordings / f"{safe}.jsonl"


def _row(reply: ModelReply, key: str) -> dict[str, Any]:
    return {
        "key": key,
        "model_id": reply.model_id,
        "prompt_version": reply.prompt_version,
        "content": reply.content,
        "usage": {
            "input_tokens": reply.input_tokens,
            "output_tokens": reply.output_tokens,
        },
        "cost_usd": reply.cost_usd,
    }


class Recorder:
    """Append-only JSONL storage for one model's recorded answers."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._rows: dict[str, ModelReply] | None = None

    def lookup(self, key: str) -> ModelReply | None:
        """Return the recorded reply for ``key``, or ``None``."""
        with self._lock:
            if self._rows is None:
                self._rows = self._read()
            return self._rows.get(key)

    def record(self, key: str, reply: ModelReply) -> None:
        """Append one row; the file is created on first record."""
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(_row(reply, key), ensure_ascii=False, sort_keys=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.write("\n")
            if self._rows is not None:
                self._rows[key] = reply

    def _read(self) -> dict[str, ModelReply]:
        rows: dict[str, ModelReply] = {}
        if not self.path.is_file():
            return rows
        try:
            lines = self.path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            msg = f"cannot read recordings {self.path}: {exc.__class__.__name__}"
            raise ConfigurationError(msg) from None
        for number, line in enumerate(lines, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
                key = row["key"]
                usage = row.get("usage") or {}
                reply = ModelReply(
                    content=row["content"],
                    model_id=row["model_id"],
                    prompt_version=row["prompt_version"],
                    input_tokens=usage.get("input_tokens"),
                    output_tokens=usage.get("output_tokens"),
                    cost_usd=row.get("cost_usd"),
                )
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
                msg = f"corrupt recording at {self.path}:{number}: {exc.__class__.__name__}"
                raise ConfigurationError(msg) from None
            rows[key] = reply
        return rows

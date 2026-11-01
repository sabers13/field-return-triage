"""The first step of ``make all``: the committed data is the data we think it is.

NHTSA rebuilds its files, so the committed derived files are the source of truth
(``PLAN.md`` section 5). ``data/CHECKSUMS.txt`` records the sha256 of every one of them;
this check recomputes those hashes and names any file that changed or disappeared. It is
fast, offline and runs before the index, the trend and the results.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Final

__all__ = ["DEFAULT_CHECKSUMS", "CheckResult", "check_data"]

DEFAULT_CHECKSUMS: Final[Path] = Path("data/CHECKSUMS.txt")


class CheckResult:
    """What the data check found."""

    def __init__(self, checked: int, failures: list[str]) -> None:
        self.checked = checked
        self.failures = failures

    @property
    def ok(self) -> bool:
        return not self.failures


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check_data(checksums: Path = DEFAULT_CHECKSUMS) -> CheckResult:
    """Recompute every listed sha256; return the count and the failures."""
    if not checksums.is_file():
        return CheckResult(0, [f"{checksums} is missing"])

    failures: list[str] = []
    checked = 0
    for number, raw in enumerate(checksums.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or len(parts[0]) != 64:
            failures.append(f"{checksums}:{number}: not '<sha256>  <path>'")
            continue
        expected, name = parts[0].lower(), parts[1].strip()
        path = Path(name)
        if not path.is_file():
            failures.append(f"{name}: missing")
            continue
        checked += 1
        actual = _hash(path)
        if actual != expected:
            failures.append(
                f"{name}: sha256 mismatch (expected {expected[:12]}..., got {actual[:12]}...)"
            )
    return CheckResult(checked, failures)

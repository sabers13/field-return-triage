#!/usr/bin/env python3
"""``make fetch-data``: resolve the five NHTSA inputs, downloading only when needed.

The pinned snapshot under ``[snapshot_dir]`` is used when every sha256 matches. Anything
missing or changed is downloaded into ``data/raw/`` (gitignored); a changed checksum is
printed as a warning, never treated as a stop. No credential is read or printed.
"""

from __future__ import annotations

import sys

from field_return_triage.data.fetch import ensure_inputs
from field_return_triage.data.spec import DEFAULT_SPEC_PATH, load_spec


def main() -> int:
    spec = load_spec(DEFAULT_SPEC_PATH)
    result = ensure_inputs(spec)
    for name, item in sorted(result.files.items()):
        state = "checksum OK" if item.matched else "checksum CHANGED"
        print(f"{name}: {item.source} ({state}) -> {item.path}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

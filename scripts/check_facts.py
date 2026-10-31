#!/usr/bin/env python3
"""Check that published numbers exist in the results file that proves them.

Adapted from which-ai-model (same author, MIT). `make facts` (and therefore
`make release-check`) runs this. Two sources are checked once the docs lane (R9) has
built them:

1. **README.md**, the table between ``<!-- facts:start -->`` and ``<!-- facts:end -->``.
   Every row names one file under ``results/`` and the exact text that file must contain.
2. **project-facts.yml**, every ``numbers`` entry. Each entry names a file and the text
   it contains; every number written in a bullet's prose must be one of that bullet's
   declared entries, so a new number cannot appear without a file that proves it.

The check is deliberately literal (substring search on the file), so the README table
carries a "proof text" column and the YAML carries ``contains``. It needs no third-party
package and opens no socket.

Scaffold behaviour: while ``project-facts.yml`` does not exist, there are no published
numbers yet, so the script says so and passes. The moment the file lands, the full check
below applies - the scaffold can never pass the release gate by staying empty by accident.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

README = ROOT / "README.md"
FACTS = ROOT / "project-facts.yml"

START = "<!-- facts:start -->"
END = "<!-- facts:end -->"

NUMBER = re.compile(r"(?<![\w.])-?\d[\d,]*(?:\.\d+)?")
BACKTICK = re.compile(r"`([^`]+)`")
INLINE_NUMBER = re.compile(
    r'-\s*\{\s*value:\s*"(?P<value>[^"]+)"\s*,\s*'
    r'file:\s*"(?P<file>[^"]+)"\s*,\s*'
    r'contains:\s*"(?P<contains>[^"]+)"\s*\}'
)
RESOURCE_LINE = re.compile(r"^\s*-\s*\{\s*name:", re.MULTILINE)

REQUIRED_FILES = (
    "README.md",
    "METHOD.md",
    "THIRD_PARTY.md",
    "CHANGELOG.md",
    "project-facts.yml",
    "LICENSE",
)

ALLOWED_TAGS = {
    "python",
    "sql",
    "ml",
    "stats",
    "viz",
    "bi",
    "etl",
    "data_engineering",
    "testing",
    "ci",
    "docker",
    "api",
    "backend",
    "frontend",
    "typescript",
    "llm",
    "nlp",
    "agents",
    "automation",
    "scraping",
    "devops",
    "observability",
    "bayesian",
    "deep_learning",
    "simulation",
    "concurrency",
    "desktop",
    "audio",
    "orchestration",
    "latex",
}


class Problems:
    """Collect failures and print them once, instead of failing on the first."""

    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, message: str) -> None:
        self.items.append(message)

    def report(self, checked: int) -> int:
        if not self.items:
            print(f"facts: {checked} checked, all present in the named results files")
            return 0
        print(f"facts: {len(self.items)} problem(s)", file=sys.stderr)
        for item in self.items:
            print(f"  - {item}", file=sys.stderr)
        return 1


def _read(path: Path, problems: Problems) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        problems.add(f"{path.relative_to(ROOT)}: missing")
        return None


def _file_text(relative: str, problems: Problems, cache: dict[str, str | None]) -> str | None:
    if relative not in cache:
        path = ROOT / relative
        if not path.is_file():
            problems.add(f"{relative}: named as a source but the file does not exist")
            cache[relative] = None
        else:
            cache[relative] = path.read_text(encoding="utf-8")
    return cache[relative]


def check_required_files(problems: Problems) -> None:
    for name in REQUIRED_FILES:
        if not (ROOT / name).is_file():
            problems.add(f"{name}: required release file is missing")


def check_readme(problems: Problems, cache: dict[str, str | None]) -> int:
    text = _read(README, problems)
    if text is None:
        return 0
    start, end = text.find(START), text.find(END)
    if start < 0 or end < 0 or end < start:
        problems.add("README.md: results table markers (<!-- facts:start/end -->) are missing")
        return 0

    checked = 0
    for line in text[start:end].splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4:
            problems.add(f"README.md: table row needs value, file and proof text: {line.strip()}")
            continue
        label, value, source, proof = cells[0], cells[1], cells[2], cells[3]
        if label in {"Result"} or value == "Value":
            continue  # Header row.
        if set(cells[0]) <= set("-: ") and set(cells[1]) <= set("-: "):
            continue  # Markdown separator row.
        paths = [item for item in BACKTICK.findall(source) if item.startswith("results/")]
        if len(paths) != 1:
            problems.add(f"README.md: row '{label}' must name exactly one results/ file")
            continue
        relative = paths[0]
        expected = proof.strip("`").strip()
        if not expected:
            problems.add(f"README.md: row '{label}' has no proof text")
            continue
        body = _file_text(relative, problems, cache)
        if body is None:
            continue
        if expected not in body:
            problems.add(f"README.md: '{expected}' from row '{label}' is not in {relative}")
            continue
        for token in NUMBER.findall(value):
            if token not in expected and token not in body:
                problems.add(f"README.md: number {token} from row '{label}' is not in {relative}")
        checked += 1

    for needle in (
        "https://sabersojudi.com/field-return-triage/",
        "https://github.com/sabers13/field-return-triage",
        "results/page/screenshots/",
        "results/SUMMARY.md",
    ):
        if needle not in text:
            problems.add(f"README.md: expected link or slot '{needle}' is missing")
    return checked


def check_facts(problems: Problems, cache: dict[str, str | None]) -> int:
    text = _read(FACTS, problems)
    if text is None:
        return 0

    checked = 0
    entries = list(INLINE_NUMBER.finditer(text))
    if text.count("value:") != len(entries):
        problems.add(
            "project-facts.yml: every numbers entry must use one inline "
            "{ value: ..., file: ..., contains: ... } line"
        )
    for match in entries:
        value, relative, contains = (
            match.group("value"),
            match.group("file"),
            match.group("contains"),
        )
        body = _file_text(relative, problems, cache)
        if body is None:
            continue
        if contains not in body:
            problems.add(f"project-facts.yml: '{contains}' for {value} is not in {relative}")
            continue
        checked += 1

    for required in (
        'title: "Field Return Triage"',
        "slug: field-return-triage",
        "repo: https://github.com/sabers13/field-return-triage",
        "live_url: https://sabersojudi.com/field-return-triage/",
    ):
        if required not in text:
            problems.add(f"project-facts.yml: expected '{required}'")

    tags = re.search(r"^tags:\s*\[(?P<tags>[^\]]*)\]", text, re.MULTILINE)
    if tags is None:
        problems.add("project-facts.yml: tags list is missing")
    else:
        parsed = {tag.strip() for tag in tags.group("tags").split(",") if tag.strip()}
        unknown = sorted(parsed - ALLOWED_TAGS)
        if unknown:
            problems.add(f"project-facts.yml: tags outside the allowed list: {unknown}")

    claims = re.search(r"^claim_limits:\s*\"(?P<text>.+)\"$", text, re.MULTILINE)
    if claims is None:
        problems.add("project-facts.yml: claim_limits is missing or not a single quoted line")

    if not RESOURCE_LINE.search(text):
        problems.add("project-facts.yml: resources list is empty")
    for line in text.splitlines():
        if RESOURCE_LINE.match(line):
            for key in ("name:", "owner:", "licence:", "url:", "used_as:"):
                if key not in line:
                    problems.add(f"project-facts.yml: resource line lacks {key} {line.strip()}")

    kinds = re.findall(r"^\s*-\s*kind:\s*(\w+)", text, re.MULTILINE)
    if kinds != ["outcome", "technical", "stack"]:
        problems.add(f"project-facts.yml: bullets must be outcome, technical, stack; got {kinds}")

    for block in re.split(r"^\s*-\s*kind:", text, flags=re.MULTILINE)[1:]:
        prose = re.search(r"^\s*text:\s*\"(?P<text>.*)\"$", block, re.MULTILINE)
        declared = list(INLINE_NUMBER.finditer(block))
        if prose is None:
            problems.add("project-facts.yml: a bullet has no text line")
            continue
        spelled = {match.group("value").strip("$%") for match in declared}
        spelled |= {match.group("contains").strip("$%") for match in declared}
        for token in NUMBER.findall(prose.group("text")):
            bare = token.strip("$%")
            if not any(bare == item or bare in item for item in spelled):
                problems.add(f"project-facts.yml: bullet number {bare} has no declared file entry")
    return checked


def main() -> int:
    if not FACTS.is_file():
        print("facts: project-facts.yml not built yet (lane R9); no published numbers to check")
        return 0
    problems = Problems()
    check_required_files(problems)
    cache: dict[str, str | None] = {}
    checked = check_readme(problems, cache) + check_facts(problems, cache)
    return problems.report(checked)


if __name__ == "__main__":
    raise SystemExit(main())

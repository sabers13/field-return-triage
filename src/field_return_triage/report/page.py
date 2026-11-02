"""Inline the page data, styles and script into one offline HTML file.

The built page is a single file: ``dist/field-return-triage/index.html``. It carries
its data in a ``<script type="application/json">`` block and its CSS and JS inline, so
opening it with ``file://`` needs no server, no font download and no CDN. The only
external link is the project's GitHub page.

``build_page`` refuses a template that would fetch a stylesheet, script, font or image
over the network. That check is the offline promise, enforced at build time.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Final

__all__ = ["DIST", "GITHUB_URL", "PAGE_DATA", "TEMPLATE", "build_page"]

GITHUB_URL: Final = "https://github.com/sabers13/field-return-triage"
PAGE_DATA: Final = Path("results/page/page-data.json")
TEMPLATE: Final = Path("web/index.html")
STYLE: Final = Path("web/page.css")
SCRIPT: Final = Path("web/page.js")
DIST: Final = Path("dist/field-return-triage/index.html")

_STYLE_MARKER: Final = "<!-- build:style -->"
_DATA_MARKER: Final = "<!-- build:data -->"
_SCRIPT_MARKER: Final = "<!-- build:script -->"

#: Any of these in the built page means something would load over the network.
_REMOTE_ASSET = re.compile(
    r"""(?:src|href)\s*=\s*["'](https?://[^"']+)["']"""
    r"""|url\(\s*["']?(https?://[^)"']+)""",
    re.IGNORECASE,
)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"page: missing {path}; run from the repository root") from exc


def _check_offline(html: str) -> None:
    """Fail the build if the page links anything over the network except GitHub."""
    for match in _REMOTE_ASSET.finditer(html):
        url = match.group(1) or match.group(2) or ""
        if url.rstrip("/") in {GITHUB_URL, GITHUB_URL + "/"}:
            continue
        raise ValueError(f"page: the built page would fetch {url}; keep it offline")


def build_page(data_path: Path = PAGE_DATA, out: Path = DIST) -> Path:
    """Inline data, style and script into ``out`` and return the written path."""
    template = _read(TEMPLATE)
    for marker in (_STYLE_MARKER, _DATA_MARKER, _SCRIPT_MARKER):
        if marker not in template:
            raise ValueError(f"page: {TEMPLATE} is missing the {marker} marker")

    try:
        data = json.loads(_read(data_path))
    except json.JSONDecodeError as exc:
        raise ValueError(f"page: {data_path} is not valid JSON: {exc}") from exc

    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = template.replace(_STYLE_MARKER, f"<style>\n{_read(STYLE)}\n</style>")
    html = html.replace(
        _DATA_MARKER,
        f'<script type="application/json" id="page-data">{payload}</script>',
    )
    html = html.replace(_SCRIPT_MARKER, f"<script>\n{_read(SCRIPT)}\n</script>")

    _check_offline(html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out

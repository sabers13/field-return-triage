"""Inline the page data, styles and script into one offline HTML file.

The built page is a single file: ``dist/field-return-triage/index.html``. It carries
its data in a ``<script type="application/json">`` block and its CSS and JS inline, so
opening it with ``file://`` needs no server, font download or CDN. External
navigation is limited to GitHub and the portfolio.

``build_page`` refuses a template that would fetch a stylesheet, script, font or image
over the network. That check is the offline promise, enforced at build time.
"""

from __future__ import annotations

import base64
import json
import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Final

__all__ = ["DIST", "GITHUB_URL", "PAGE_DATA", "TEMPLATE", "build_page"]

GITHUB_URL: Final = "https://github.com/sabers13/field-return-triage"
PAGE_DATA: Final = Path("results/page/page-data.json")
TEMPLATE: Final = Path("web/index.html")
STYLE: Final = Path("web/page.css")
SCRIPT: Final = Path("web/page.js")
FONT: Final = Path("web/fonts/inter-latin-wght-normal.woff2")
FONT_LICENCE: Final = Path("web/fonts/OFL-inter.txt")
DIST: Final = Path("dist/field-return-triage/index.html")

_STYLE_MARKER: Final = "<!-- build:style -->"
_DATA_MARKER: Final = "<!-- build:data -->"
_SCRIPT_MARKER: Final = "<!-- build:script -->"

_CSS_REMOTE = re.compile(r"url\(\s*[\"']?(?:https?:)?//", re.IGNORECASE)
_NAVIGATION: Final = frozenset(
    {
        GITHUB_URL,
        "https://github.com/sabers13",
        "https://sabersojudi.com/",
        "https://sabersojudi.com/#contact",
    }
)


class _OfflineCheck(HTMLParser):
    """Distinguish a clicked destination from a network-loaded resource."""

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for name, value in attrs:
            if name not in {"src", "href", "srcset", "poster", "action"} or not value:
                continue
            if not re.match(r"(?:https?:)?//", value, re.IGNORECASE):
                continue
            if tag == "a" and name == "href" and value in _NAVIGATION:
                continue
            raise ValueError(f"page: the built page would fetch {value}; keep it offline")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"page: missing {path}; run from the repository root") from exc


def _check_offline(html: str) -> None:
    """Permit intentional navigation, while keeping all page assets offline."""
    _OfflineCheck().feed(html)
    if _CSS_REMOTE.search(html):
        raise ValueError("page: remote CSS asset; keep it offline")


def _inline_style() -> str:
    """Embed the local, licensed portfolio font in the standalone page."""
    encoded = base64.b64encode(FONT.read_bytes()).decode("ascii")
    style = _read(STYLE).replace(
        'url("fonts/inter-latin-wght-normal.woff2")', f'url("data:font/woff2;base64,{encoded}")'
    )
    licence = _read(FONT_LICENCE).replace("*/", "* /")
    return f"/* Inter font licence:\n{licence}\n*/\n{style}"


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
    html = template.replace(_STYLE_MARKER, f"<style>\n{_inline_style()}\n</style>")
    html = html.replace(
        _DATA_MARKER,
        f'<script type="application/json" id="page-data">{payload}</script>',
    )
    html = html.replace(_SCRIPT_MARKER, f"<script>\n{_read(SCRIPT)}\n</script>")
    attribution = "\n\n".join(
        _read(path)
        for path in (
            Path("THIRD_PARTY.md"),
            FONT_LICENCE,
            Path("web/fonts/LICENSE-feather.txt"),
        )
    )
    html = html.replace("<!-- build:credits -->", escape(attribution))

    _check_offline(html)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return out

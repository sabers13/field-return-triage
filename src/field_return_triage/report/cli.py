"""``make page-data`` and ``make page``: the two page build steps.

``page-data`` writes ``results/page/page-data.json`` and then refreshes
``results/MANIFEST.sha256`` so the new file is covered by the same manifest as every
other results file. ``page`` inlines the data, ``web/page.css`` and ``web/page.js`` into
``dist/field-return-triage/index.html``. Both run offline.
"""

from __future__ import annotations

import typer

from field_return_triage.pipeline.summary import write_manifest
from field_return_triage.report.page import build_page
from field_return_triage.report.page_data import RESULTS, write_page_data

__all__ = ["app", "main", "page_data_main", "page_main"]


def page_data_main() -> None:
    """Build ``results/page/page-data.json`` and keep the manifest current."""
    path = write_page_data()
    manifest = write_manifest(RESULTS)
    typer.echo(f"page-data: {path} ({len(path.read_bytes())} bytes); manifest {manifest}")


def page_main() -> None:
    """Build the single offline file at ``dist/field-return-triage/index.html``."""
    path = build_page()
    typer.echo(f"page: {path} ({len(path.read_bytes())} bytes)")


def main() -> None:
    """Both steps, in order (the documented ``main()`` entry point)."""
    page_data_main()
    page_main()


app = typer.Typer(
    name="frt-page",
    help="Build the page data and the static page (lane R8).",
    add_completion=False,
)


@app.command("page-data")
def _page_data_command() -> None:
    """Write results/page/page-data.json (make page-data)."""
    page_data_main()


@app.command("page")
def _page_command() -> None:
    """Write dist/field-return-triage/index.html (make page)."""
    page_main()


if __name__ == "__main__":  # pragma: no cover - make entry point
    app()

"""The page lane (R8): ``results/page/page-data.json`` and the static page.

Public surface (``docs/INTERFACES.md`` section 9):

* :mod:`report.page_data` - read the committed results and build the page's data;
* :mod:`report.page` - inline that data, the styles and the script into one HTML file;
* :mod:`report.cli` - the ``make page-data`` and ``make page`` commands.

Every number the page renders comes from a committed file under ``results/``. The only
other input is ``config/models.lock.toml``, quoted as provenance (which which-ai-model
card picked each model), never as a result.
"""

from __future__ import annotations

from field_return_triage.pipeline.summary import build_summary, write_manifest
from field_return_triage.report.page import DIST, build_page
from field_return_triage.report.page_data import PAGE_DATA, build_page_data, write_page_data

__all__ = [
    "DIST",
    "PAGE_DATA",
    "build_page",
    "build_page_data",
    "build_summary",
    "write_manifest",
    "write_page_data",
]

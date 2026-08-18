"""Inject the data payload into the dashboard template.

Keeps the same rule as the rest of the project: no figure on the page is typed by
hand. Rebuild the warehouse, regenerate the payload, rerun this, and every number
and chart on the page moves with the data.
"""

import sys

from pipeline.config import ROOT

TEMPLATE = ROOT / "dashboards" / "template.html"
DATA = ROOT / "dashboards" / "dashboard_data.json"
OUT = ROOT / "dashboards" / "index.html"


def main() -> int:
    for path in (TEMPLATE, DATA):
        if not path.exists():
            print(f"missing {path} -- run analysis.build_dashboard_data first", file=sys.stderr)
            return 1
    html = TEMPLATE.read_text().replace("__DATA__", DATA.read_text())
    OUT.write_text(html)
    print(f"{OUT.stat().st_size/1024:.1f} KB -> {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

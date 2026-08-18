"""Build the DuckDB warehouse from the parquet files.

Runs every .sql file under sql/ in lexical order -- directories are numbered by
layer (staging, dimensions, facts, marts) and files within a layer are numbered
by dependency. There is no DAG resolver here on purpose: with a dozen models the
numbering is easier to read than a dependency graph, and it fails loudly and in
order when something upstream is missing.

Two placeholders are substituted before execution:

    ${DATA_RAW}       data/raw
    ${DATA_PARQUET}   data/parquet
"""

import re
import sys
import time
from pathlib import Path

import duckdb

from pipeline.config import PARQUET_DIR, RAW_DIR, ROOT, WAREHOUSE, WAREHOUSE_DIR

SQL_DIR = ROOT / "sql"
OBJECT_RE = re.compile(
    r"CREATE\s+OR\s+REPLACE\s+(?:TABLE|VIEW)\s+([a-z_0-9]+)", re.IGNORECASE
)


def sql_files() -> list[Path]:
    return sorted(
        (p for p in SQL_DIR.rglob("*.sql") if p.parent.name != "tests"),
        key=lambda p: (p.parent.name, p.name),
    )


def render(path: Path) -> str:
    return (
        path.read_text()
        .replace("${DATA_RAW}", str(RAW_DIR))
        .replace("${DATA_PARQUET}", str(PARQUET_DIR))
    )


def main() -> int:
    if not any(PARQUET_DIR.rglob("*.parquet")):
        print("no parquet found -- run pipeline.download then pipeline.ingest first",
              file=sys.stderr)
        return 1

    WAREHOUSE_DIR.mkdir(parents=True, exist_ok=True)
    # Full rebuild every time. CREATE OR REPLACE leaves the old blocks behind in
    # an existing file, so a warehouse rebuilt in place grows by several GB per
    # run and its reported size stops meaning anything.
    WAREHOUSE.unlink(missing_ok=True)
    con = duckdb.connect(str(WAREHOUSE))
    con.execute("INSTALL icu; LOAD icu;")
    con.execute("PRAGMA threads=8")
    # TIMESTAMPTZ stores an instant, but it RENDERS in the session timezone.
    # Pinning to UTC means a query returns the same text on any machine.
    con.execute("SET TimeZone='UTC'")

    files = sql_files()
    print(f"building {WAREHOUSE.relative_to(ROOT)} from {len(files)} models\n")

    for path in files:
        label = f"{path.parent.name}/{path.name}"
        started = time.time()
        try:
            con.execute(render(path))
        except duckdb.Error as e:
            print(f"  FAILED  {label}\n\n{e}", file=sys.stderr)
            return 1
        elapsed = time.time() - started

        match = OBJECT_RE.search(path.read_text())
        rows = ""
        if match:
            try:
                n = con.execute(f"SELECT count(*) FROM {match.group(1)}").fetchone()[0]
                rows = f"{n:>12,} rows"
            except duckdb.Error:
                rows = ""
        print(f"  ok  {label:<42} {elapsed:6.1f}s {rows}")

    size = WAREHOUSE.stat().st_size / 1e9
    print(f"\nwarehouse built: {size:.2f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Convert the downloaded monthly zips into typed, columnar parquet.

Why this step exists: the raw CSVs are ~247 MB each, 110 columns wide, and
every numeric field is quoted text ("12.00"). Sixty of them is roughly 15 GB
of text that no query can touch without re-parsing. Narrowing to the 49
columns the warehouse uses and writing typed parquet cuts that by well over
an order of magnitude and makes column scans essentially free.

Output is Hive-partitioned so DuckDB can prune whole months from a query:

    data/parquet/year=2021/month=1/flights.parquet
"""

import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

import duckdb

from pipeline.config import PARQUET_DIR, RAW_DIR, SCHEMA, months

# BTS ships the CSVs in latin-1; a handful of city names carry accented
# characters that are not valid UTF-8.
ENCODING = "latin-1"


def cast_expr(source: str, target: str, kind: str) -> str:
    """SQL that turns one all-varchar CSV column into its warehouse type.

    TRY_CAST throughout: cancelled flights leave dep_time, arr_delay and the
    rest empty, and a hard cast would fail the whole file on those rows.
    """
    col = f'"{source}"'
    if kind == "int":
        expr = f"TRY_CAST({col} AS INTEGER)"
    elif kind == "date":
        expr = f"TRY_CAST({col} AS DATE)"
    elif kind == "hhmm":
        # Stored zero-padded ("0856"); an INTEGER cast is lossless for the
        # HHMM arithmetic done in the warehouse layer.
        expr = f"TRY_CAST({col} AS INTEGER)"
    elif kind == "minutes":
        # "12.00" -> 12. Every BTS duration is a whole number of minutes.
        expr = f"TRY_CAST(TRY_CAST({col} AS DOUBLE) AS INTEGER)"
    elif kind == "num":
        expr = f"TRY_CAST({col} AS DOUBLE)"
    elif kind == "bool":
        expr = f"TRY_CAST({col} AS DOUBLE) = 1"
    elif kind == "str":
        # Empty string and whitespace are both 'missing' in this feed.
        expr = f"NULLIF(TRIM({col}), '')"
    else:
        raise ValueError(f"unknown type {kind!r} for {source}")
    return f"{expr} AS {target}"


SELECT_LIST = ",\n    ".join(cast_expr(s, t, k) for s, t, k in SCHEMA)


def ingest_month(con: duckdb.DuckDBPyConnection, year: int, month: int) -> int:
    """Extract, cast and write one month. Returns the row count."""
    zip_path = RAW_DIR / f"{year}_{month}.zip"
    out_dir = PARQUET_DIR / f"year={year}" / f"month={month}"
    out_file = out_dir / "flights.parquet"
    out_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zip_path) as z:
        csv_name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        # Extract to scratch rather than streaming: DuckDB's parallel CSV
        # reader needs a seekable file, and the temp copy is deleted below.
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "flights.csv"
            with z.open(csv_name) as src, open(csv_path, "wb") as dst:
                shutil.copyfileobj(src, dst, length=1 << 22)

            con.execute(f"""
                COPY (
                    SELECT
                    {SELECT_LIST}
                    FROM read_csv(
                        '{csv_path}',
                        header = true,
                        all_varchar = true,
                        encoding = '{ENCODING}',
                        ignore_errors = false
                    )
                ) TO '{out_file}' (FORMAT parquet, COMPRESSION zstd)
            """)

    return con.execute(f"SELECT count(*) FROM read_parquet('{out_file}')").fetchone()[0]


def main() -> int:
    PARQUET_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("PRAGMA threads=8")

    todo = [(y, m) for y, m in months() if (RAW_DIR / f"{y}_{m}.zip").exists()]
    missing = [(y, m) for y, m in months() if not (RAW_DIR / f"{y}_{m}.zip").exists()]
    if missing:
        print(f"warning: {len(missing)} months not downloaded yet, skipping", file=sys.stderr)

    total = 0
    for i, (year, month) in enumerate(todo, 1):
        out_file = PARQUET_DIR / f"year={year}" / f"month={month}" / "flights.parquet"
        if out_file.exists():
            rows = con.execute(f"SELECT count(*) FROM read_parquet('{out_file}')").fetchone()[0]
            status = "cached"
        else:
            rows = ingest_month(con, year, month)
            status = "written"
        total += rows
        size = out_file.stat().st_size / 1e6
        print(f"[{i:2d}/{len(todo)}] {year}-{month:02d}  {status:<8} "
              f"{rows:>8,} rows  {size:6.1f} MB", flush=True)

    print(f"\n{total:,} flights across {len(todo)} months")
    parquet_bytes = sum(p.stat().st_size for p in PARQUET_DIR.rglob("*.parquet"))
    print(f"parquet footprint: {parquet_bytes / 1e9:.2f} GB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

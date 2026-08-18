"""Export the marts as CSV for Power BI and Tableau.

The warehouse is 10 GB and neither tool wants to consume it directly. What they
need are the aggregates, which are small: the whole export is a few dozen MB and
imports in seconds.

mart_airport_daily is the exception -- 615k rows is fine for Power BI but slow to
refresh from CSV in Tableau Public, so it ships pre-filtered to the stations that
carry meaningful volume.
"""

import sys

import duckdb

from pipeline.config import ROOT, WAREHOUSE

EXPORT_DIR = ROOT / "dashboards" / "data"

EXPORTS = {
    "carrier_monthly": "SELECT * FROM mart_carrier_monthly",
    "route_reliability": """
        SELECT * FROM mart_route_reliability
        WHERE flights >= 1000 ORDER BY flights DESC
    """,
    "turn_slack_opportunity": "SELECT * FROM mart_turn_slack_opportunity",
    "airport_daily": """
        SELECT d.* FROM mart_airport_daily d
        JOIN dim_airport a USING (airport_code)
        WHERE a.size_band IN ('Large', 'Medium')
    """,
    "dim_airport": "SELECT * FROM dim_airport",
    "dim_carrier": "SELECT * FROM dim_carrier",
    "dim_date": "SELECT * FROM dim_date",
    # Cascade summaries rather than the 3.7M-row fact: these are the shapes the
    # dashboards actually plot.
    "cascade_by_hour": """
        SELECT root_dep_hour_local AS dep_hour, carrier, carrier_name, carrier_type,
               count(*) AS root_delays,
               round(avg(downstream_legs), 3) AS avg_downstream_legs,
               round(avg(downstream_delay_minutes), 2) AS avg_downstream_minutes,
               round(avg(amplification_ratio), 3) AS avg_amplification,
               sum(total_cascade_minutes) AS total_cascade_minutes,
               round(sum(total_cascade_cost_usd), 0) AS total_cascade_cost_usd
        FROM mart_cascade GROUP BY ALL ORDER BY dep_hour, carrier
    """,
    "cascade_length_distribution": """
        SELECT downstream_legs AS cascade_length, carrier_type, count(*) AS cascades,
               round(avg(downstream_delay_minutes), 1) AS avg_downstream_minutes,
               round(avg(amplification_ratio), 3) AS avg_amplification
        FROM mart_cascade GROUP BY ALL ORDER BY cascade_length
    """,
    "buffer_efficiency_by_hour": """
        SELECT sched_dep_hour_local AS turn_hour, carrier, count(*) AS turns,
               round(sum(greatest(coalesce(prev_arr_delay,0) - turn_slack_minutes, 0)), 0)
                   AS predicted_inherited_base,
               round(sum(greatest(coalesce(prev_arr_delay,0) - (turn_slack_minutes+10), 0)), 0)
                   AS predicted_inherited_plus_10,
               round((sum(greatest(coalesce(prev_arr_delay,0) - turn_slack_minutes, 0))
                    - sum(greatest(coalesce(prev_arr_delay,0) - (turn_slack_minutes+10), 0)))
                     / (10.0*count(*)), 4) AS buffer_efficiency
        FROM fct_rotation_leg WHERE is_continuation
        GROUP BY ALL ORDER BY turn_hour, carrier
    """,
}


def main() -> int:
    if not WAREHOUSE.exists():
        print("warehouse not built", file=sys.stderr)
        return 1
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    con.execute("LOAD icu;")
    con.execute("SET TimeZone='UTC'")

    total = 0
    for name, sql in EXPORTS.items():
        path = EXPORT_DIR / f"{name}.csv"
        con.execute(f"COPY ({sql}) TO '{path}' (HEADER, DELIMITER ',')")
        rows = con.execute(f"SELECT count(*) FROM ({sql})").fetchone()[0]
        size = path.stat().st_size / 1e6
        total += path.stat().st_size
        print(f"  {name:<30} {rows:>9,} rows  {size:6.1f} MB")

    print(f"\n{len(EXPORTS)} files, {total/1e6:.1f} MB -> {EXPORT_DIR.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

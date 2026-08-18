"""Build the JSON payload the static dashboard embeds.

The dashboard ships as a single self-contained HTML file with no network access,
so the data has to travel inside it. Everything here is pre-aggregated to the
shape a chart actually plots -- the largest series is 24 points -- which keeps
the whole payload under 30 KB.
"""

import json
import sys

import duckdb

from pipeline.config import ROOT, WAREHOUSE

BLOCK_MINUTE_USD = 98.41


def main() -> int:
    if not WAREHOUSE.exists():
        print("warehouse not built", file=sys.stderr)
        return 1
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    con.execute("LOAD icu;")
    con.execute("SET TimeZone='UTC'")
    rows = lambda sql: con.execute(sql).df().to_dict("records")
    scalar = lambda sql: con.execute(sql).fetchone()

    flights, carriers, airports, tails, d0, d1 = scalar("""
        SELECT count(*), count(DISTINCT carrier), count(DISTINCT origin),
               count(DISTINCT tail_number), min(flight_date)::VARCHAR, max(flight_date)::VARCHAR
        FROM fct_flight""")
    a14, cf, cancel, mean_d, p90 = scalar("""
        SELECT 100.0*avg(is_on_time_a14::INT), 100.0*avg(completed::INT),
               100.0*avg(cancelled::INT), avg(arr_delay) FILTER (WHERE completed),
               quantile_cont(arr_delay,0.90) FILTER (WHERE completed)
        FROM fct_flight""")
    root_m, inh_m = scalar("""
        SELECT sum(root_delay_minutes)/1e6, sum(inherited_delay_minutes)/1e6 FROM fct_flight""")
    corr, pred, rep, turns_n = scalar("""
        SELECT corr(predicted_inherited_minutes, inherited_delay_minutes),
               avg(predicted_inherited_minutes), avg(inherited_delay_minutes), count(*)
        FROM fct_rotation_leg WHERE is_continuation AND prev_arr_delay > 15""")

    payload = {
        "meta": {
            "flights": int(flights), "carriers": int(carriers), "airports": int(airports),
            "airframes": int(tails), "from": d0, "to": d1,
            "a14": round(a14, 2), "completion": round(cf, 2), "cancel": round(cancel, 2),
            "mean_delay": round(mean_d, 1), "p90_delay": round(p90, 0),
            "root_m": round(root_m, 1), "inherited_m": round(inh_m, 1),
            "inherited_pct": round(100 * inh_m / (root_m + inh_m), 1),
            "inherited_cost_bn": round(inh_m * BLOCK_MINUTE_USD / 1000, 2),
            "corr": round(corr, 3), "model_pred": round(pred, 1), "model_reported": round(rep, 1),
            "model_turns": int(turns_n), "block_minute_usd": BLOCK_MINUTE_USD,
        },
        # Finding 3: damage done by one root delay, by hour of day
        "cascade_by_hour": rows("""
            SELECT root_dep_hour_local AS hour, count(*) AS roots,
                   round(avg(downstream_legs),3) AS legs,
                   round(avg(downstream_delay_minutes),1) AS minutes,
                   round(avg(amplification_ratio),3) AS amplification
            FROM mart_cascade WHERE root_dep_hour_local BETWEEN 5 AND 22
            GROUP BY 1 ORDER BY 1"""),
        # Finding 4: what a buffer minute buys, by hour of day
        "buffer_by_hour": rows("""
            SELECT sched_dep_hour_local AS hour, count(*) AS turns,
                   round((sum(greatest(coalesce(prev_arr_delay,0) - turn_slack_minutes,0))
                        - sum(greatest(coalesce(prev_arr_delay,0) - (turn_slack_minutes+10),0)))
                         / (10.0*count(*)), 4) AS efficiency
            FROM fct_rotation_leg WHERE is_continuation AND sched_dep_hour_local BETWEEN 5 AND 22
            GROUP BY 1 ORDER BY 1"""),
        # Finding 2: dose-response of slack on inherited delay
        "slack_response": rows("""
            SELECT least(floor(turn_slack_minutes/15),6)*15 AS slack_floor,
                   count(*) AS turns,
                   round(avg(inherited_delay_minutes),1) AS avg_inherited,
                   round(100.0*avg((dep_delay>=15)::INT),1) AS pct_late
            FROM fct_rotation_leg
            WHERE is_continuation AND prev_arr_delay BETWEEN 30 AND 60
            GROUP BY 1 ORDER BY 1"""),
        "cascade_length": rows("""
            SELECT downstream_legs AS length, count(*) AS cascades,
                   round(avg(downstream_delay_minutes),1) AS avg_minutes
            FROM mart_cascade WHERE downstream_legs <= 8
            GROUP BY 1 ORDER BY 1"""),
        "carriers": rows("""
            SELECT c.carrier_name AS name, c.carrier_type AS type,
                   sum(m.scheduled_flights) AS flights,
                   round(sum(m.scheduled_flights*m.on_time_arrival_pct)/sum(m.scheduled_flights),2) AS a14,
                   round(100.0*sum(m.inherited_delay_minutes)
                       /sum(m.root_delay_minutes+m.inherited_delay_minutes),1) AS inherited_pct
            FROM mart_carrier_monthly m JOIN dim_carrier c USING (carrier)
            GROUP BY 1,2 HAVING sum(m.scheduled_flights) > 200000 ORDER BY a14 DESC"""),
        "stations": rows("""
            SELECT carrier_name AS carrier, airport_code AS station, city,
                   turns, median_slack_minutes AS slack, tight_turn_pct AS tight,
                   minutes_saved_plus_10 AS saved,
                   round(delay_cost_avoided_usd_plus_10/1e6,1) AS cost_musd
            FROM mart_turn_slack_opportunity ORDER BY minutes_saved_plus_10 DESC LIMIT 10"""),
        "dec2022": rows("""
            SELECT flight_date::VARCHAR AS date,
                   round(100.0*avg(cancelled::INT) FILTER (WHERE carrier='WN'),1) AS southwest,
                   round(100.0*avg(cancelled::INT) FILTER (WHERE carrier<>'WN'),1) AS others
            FROM fct_flight WHERE flight_date BETWEEN DATE '2022-12-18' AND DATE '2022-12-31'
            GROUP BY 1 ORDER BY 1"""),
        "monthly": rows("""
            SELECT month_start::VARCHAR AS month,
                   round(sum(scheduled_flights*on_time_arrival_pct)/sum(scheduled_flights),2) AS a14,
                   round(100.0*sum(inherited_delay_minutes)
                       /sum(root_delay_minutes+inherited_delay_minutes),1) AS inherited_pct
            FROM mart_carrier_monthly GROUP BY 1 ORDER BY 1"""),
    }

    path = ROOT / "dashboards" / "dashboard_data.json"
    path.write_text(json.dumps(payload, separators=(",", ":")))
    print(f"{path.stat().st_size/1024:.1f} KB -> {path.relative_to(ROOT)}")
    for k, v in payload.items():
        if isinstance(v, list):
            print(f"  {k:<20} {len(v)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

-- Station performance, daily grain, from the departure side.
--
-- Includes a same-day network stress measure: the share of the day's departures
-- at this station that pushed back 15+ minutes. Station-level bad days are
-- usually weather or airspace events, and this is the field that lets an
-- analysis separate "this station is chronically tight" from "this station had
-- eleven bad days in February".

CREATE OR REPLACE TABLE mart_airport_daily AS
SELECT
    f.flight_date,
    f.origin                                                        AS airport_code,
    a.city,
    a.size_band,
    d.travel_period,
    d.is_federal_holiday,
    d.day_name,

    count(*)                                                        AS departures,
    count(DISTINCT f.carrier)                                       AS carriers_operating,
    sum(f.cancelled::INT)                                           AS cancellations,
    round(100.0 * avg(f.cancelled::INT), 2)                         AS cancellation_rate_pct,
    round(100.0 * avg((NOT f.cancelled AND f.dep_delay >= 15)::INT), 2)
                                                                    AS departures_delayed_pct,
    round(avg(f.dep_delay) FILTER (WHERE f.completed), 2)           AS avg_dep_delay_minutes,
    round(quantile_cont(f.dep_delay, 0.90) FILTER (WHERE f.completed), 1)
                                                                    AS p90_dep_delay_minutes,
    round(avg(f.taxi_out) FILTER (WHERE f.completed), 2)            AS avg_taxi_out_minutes,

    sum(f.root_delay_minutes)                                       AS root_delay_minutes,
    sum(f.inherited_delay_minutes)                                  AS inherited_delay_minutes
FROM fct_flight f
LEFT JOIN dim_airport a ON a.airport_code = f.origin
LEFT JOIN dim_date d    ON d.date_day     = f.flight_date
GROUP BY ALL;

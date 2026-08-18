-- Route scorecard. Only routes with enough flights to say anything: a route
-- flown 40 times over five years can post a 100% on-time rate and mean nothing.
-- MIN_FLIGHTS = 500 across the window, roughly two a week.

CREATE OR REPLACE TABLE mart_route_reliability AS
SELECT
    f.route,
    f.origin,
    f.dest,
    o.city                                                          AS origin_city,
    dst.city                                                        AS dest_city,
    o.size_band                                                     AS origin_size_band,
    f.carrier,
    c.carrier_name,

    count(*)                                                        AS flights,
    round(avg(f.distance_miles), 0)                                 AS distance_miles,
    round(avg(f.crs_elapsed_time), 1)                               AS avg_scheduled_block_minutes,

    round(100.0 * avg(f.is_on_time_a14::INT), 2)                    AS on_time_arrival_pct,
    round(100.0 * avg(f.cancelled::INT), 2)                         AS cancellation_rate_pct,
    round(avg(f.arr_delay) FILTER (WHERE f.completed), 2)           AS avg_arr_delay_minutes,
    round(quantile_cont(f.arr_delay, 0.90) FILTER (WHERE f.completed), 1)
                                                                    AS p90_arr_delay_minutes,
    -- Schedule padding: how much block time the carrier holds beyond what the
    -- flight actually takes. Consistently negative variance on a route means
    -- the schedule is buying its own on-time rate.
    round(avg(f.block_time_variance) FILTER (WHERE f.completed), 2)  AS avg_block_variance_minutes,
    round(avg(f.air_time) FILTER (WHERE f.completed), 1)             AS avg_air_time_minutes,

    sum(f.root_delay_minutes)                                       AS root_delay_minutes,
    sum(f.inherited_delay_minutes)                                  AS inherited_delay_minutes
FROM fct_flight f
LEFT JOIN dim_airport o   ON o.airport_code   = f.origin
LEFT JOIN dim_airport dst ON dst.airport_code = f.dest
LEFT JOIN dim_carrier c   USING (carrier)
GROUP BY ALL
HAVING count(*) >= 500;

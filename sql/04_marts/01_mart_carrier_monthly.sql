-- Carrier scorecard, monthly grain. The table a VP of Operations reads.
--
-- Every rate here has cancelled and diverted flights in the denominator.
-- Excluding them is the standard way this metric gets flattered: an airline
-- that cancels 400 flights on a bad day removes its worst outcomes from the
-- average and its on-time rate goes UP. Completion factor sits next to A14 so
-- the two cannot be read apart.

CREATE OR REPLACE TABLE mart_carrier_monthly AS
SELECT
    f.year,
    f.month,
    make_date(f.year, f.month, 1)                                   AS month_start,
    f.carrier,
    c.carrier_name,
    c.carrier_type,

    count(*)                                                        AS scheduled_flights,
    sum(f.completed::INT)                                           AS completed_flights,
    sum(f.cancelled::INT)                                           AS cancelled_flights,
    sum(f.diverted::INT)                                            AS diverted_flights,

    -- headline KPIs
    round(100.0 * avg(f.is_on_time_a14::INT), 2)                    AS on_time_arrival_pct,
    round(100.0 * avg(f.completed::INT), 2)                         AS completion_factor_pct,
    round(100.0 * avg(f.cancelled::INT), 2)                         AS cancellation_rate_pct,
    round(avg(f.arr_delay) FILTER (WHERE f.completed), 2)           AS avg_arr_delay_minutes,
    round(median(f.arr_delay) FILTER (WHERE f.completed), 1)        AS median_arr_delay_minutes,
    -- The mean is dragged by a thin tail of very long delays; the 90th
    -- percentile is what a passenger experiences on a bad day, and the gap
    -- between the two is the story on most carriers.
    round(quantile_cont(f.arr_delay, 0.90) FILTER (WHERE f.completed), 1)
                                                                    AS p90_arr_delay_minutes,

    -- delay decomposition
    sum(f.root_delay_minutes)                                       AS root_delay_minutes,
    sum(f.inherited_delay_minutes)                                  AS inherited_delay_minutes,
    sum(f.controllable_root_minutes)                                AS controllable_root_minutes,
    sum(f.external_root_minutes)                                    AS external_root_minutes,
    round(100.0 * sum(f.inherited_delay_minutes)
          / nullif(sum(f.root_delay_minutes + f.inherited_delay_minutes), 0), 1)
                                                                    AS inherited_share_pct,

    -- schedule behaviour: negative means the carrier is padding block times
    round(avg(f.block_time_variance) FILTER (WHERE f.completed), 2)  AS avg_block_variance_minutes
FROM fct_flight f
LEFT JOIN dim_carrier c USING (carrier)
GROUP BY ALL;

-- One row per scheduled flight leg, with every clock field resolved to UTC.
--
-- This is where the feed becomes analysable. BTS stores six clock fields as
-- HHMM integers in the LOCAL time of the relevant airport (0856 -> 08:56,
-- 2400 -> midnight). Comparing a departure at one airport to an arrival at
-- another is meaningless until both are instants.
--
-- Rather than reconstruct arrival timestamps from the local HHMM fields -- which
-- needs a date-wrap rule for red-eyes and gets westbound flights wrong -- the
-- arrival instants here are derived forward from the departure instant using
-- the scheduled block time and the reported delay:
--
--     sched_arr_utc  = sched_dep_utc + crs_elapsed_time
--     actual_dep_utc = sched_dep_utc + dep_delay
--     actual_arr_utc = sched_arr_utc + arr_delay
--
-- That is exact by construction and has no date-wrap edge cases. The local
-- HHMM arrival fields are kept for reporting, not arithmetic.

CREATE OR REPLACE VIEW stg_flight AS
WITH raw AS (
    SELECT * FROM read_parquet('${DATA_PARQUET}/**/*.parquet', hive_partitioning = true)
),

localised AS (
    SELECT
        r.*,
        origin_ap.timezone AS origin_tz,
        dest_ap.timezone   AS dest_tz,

        -- HHMM -> local timestamp. 2400 rolls into the next day on its own.
        (r.flight_date::TIMESTAMP
            + to_hours((r.crs_dep_time / 100)::BIGINT)
            + to_minutes((r.crs_dep_time % 100)::BIGINT)) AS sched_dep_local
    FROM raw r
    LEFT JOIN stg_airport origin_ap ON origin_ap.airport_code = r.origin
    LEFT JOIN stg_airport dest_ap   ON dest_ap.airport_code   = r.dest
)

SELECT
    -- grain: one scheduled leg
    flight_date,
    carrier,
    flight_number,
    tail_number,
    origin,
    dest,
    origin_tz,
    dest_tz,

    -- calendar
    year,
    quarter,
    month,
    day_of_month,
    day_of_week,

    -- instants
    sched_dep_local,
    sched_dep_local AT TIME ZONE origin_tz                                  AS sched_dep_utc,
    -- A handful of records (14 in 60 months) carry a NEGATIVE scheduled block
    -- time -- one has DFW-GCK scheduled to land 272 minutes before it departs.
    -- These are corrupt at source. Rather than drop the rows or let them
    -- generate impossible timestamps, the schedule is marked invalid and no
    -- arrival instant is derived from it.
    crs_elapsed_time > 0                                                    AS is_schedule_valid,
    CASE WHEN crs_elapsed_time > 0 THEN
        (sched_dep_local AT TIME ZONE origin_tz) + to_minutes(crs_elapsed_time::BIGINT)
    END                                                                     AS sched_arr_utc,
    CASE WHEN NOT cancelled THEN
        (sched_dep_local AT TIME ZONE origin_tz) + to_minutes(dep_delay::BIGINT)
    END                                                                     AS actual_dep_utc,
    CASE WHEN NOT cancelled AND NOT diverted AND crs_elapsed_time > 0 THEN
        (sched_dep_local AT TIME ZONE origin_tz)
            + to_minutes(crs_elapsed_time::BIGINT) + to_minutes(arr_delay::BIGINT)
    END                                                                     AS actual_arr_utc,

    -- local clock fields, kept for reporting
    crs_dep_time,
    dep_time,
    crs_arr_time,
    arr_time,
    dep_time_block,
    arr_time_block,

    -- performance
    dep_delay,
    dep_delay_minutes,
    dep_del15,
    arr_delay,
    arr_delay_minutes,
    arr_del15,
    taxi_out,
    taxi_in,
    crs_elapsed_time,
    actual_elapsed_time,
    air_time,
    distance_miles,
    distance_group,

    -- completion
    cancelled,
    cancellation_code,
    diverted,

    -- cause attribution, NULL unless the flight arrived 15+ minutes late
    carrier_delay,
    weather_delay,
    nas_delay,
    security_delay,
    late_aircraft_delay
FROM localised;

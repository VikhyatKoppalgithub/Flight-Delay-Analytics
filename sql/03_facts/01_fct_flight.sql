-- Flight fact. One row per scheduled leg, with the delay decomposition that
-- the rest of the project is built on.
--
-- THE CENTRAL DISTINCTION
--
-- BTS reports five delay causes. Four of them describe something that went
-- wrong with THIS flight:
--
--     carrier_delay   crew, maintenance, fuelling, baggage, catering
--     weather_delay   extreme weather that stopped this flight
--     nas_delay       air traffic control, volume, non-extreme weather
--     security_delay  screening, evacuation, breach
--
-- The fifth, late_aircraft_delay, describes something that went wrong with a
-- DIFFERENT flight -- the previous leg flown by the same airframe -- and simply
-- arrived here. It is the largest single category in most months, and treating
-- it as a cause is the most common mistake made with this dataset. It is not a
-- cause. It is the shadow of a cause that happened somewhere else, earlier.
--
-- So every delayed flight is split two ways:
--
--     root_delay_minutes       originated here
--     inherited_delay_minutes  arrived from upstream (= late_aircraft_delay)
--
-- Only root delay is addressable at this flight. Inherited delay is addressable
-- at whatever leg started it, which is what fct_rotation_leg goes and finds.
--
-- Note on NULLs: BTS populates the five cause fields ONLY when a flight arrives
-- 15 or more minutes late. They are NULL, not zero, for everything else. Summing
-- them without care silently drops every 14-minute delay from the denominator.

CREATE OR REPLACE TABLE fct_flight AS
SELECT
    -- keys
    f.flight_date,
    f.carrier,
    f.flight_number,
    f.tail_number,
    f.origin,
    f.dest,
    f.origin || '-' || f.dest                       AS route,

    -- calendar
    f.year,
    f.quarter,
    f.month,
    f.day_of_week,

    -- instants
    f.sched_dep_utc,
    f.sched_arr_utc,
    f.actual_dep_utc,
    f.actual_arr_utc,
    f.sched_dep_local,
    f.crs_dep_time,
    f.dep_time_block,
    (f.crs_dep_time / 100)::INTEGER                 AS sched_dep_hour_local,

    -- outcome
    f.cancelled,
    f.cancellation_code,
    CASE f.cancellation_code
        WHEN 'A' THEN 'Carrier'
        WHEN 'B' THEN 'Weather'
        WHEN 'C' THEN 'National Air System'
        WHEN 'D' THEN 'Security'
    END                                             AS cancellation_reason,
    f.diverted,
    NOT f.cancelled AND NOT f.diverted              AS completed,
    f.is_schedule_valid,

    -- performance
    f.dep_delay,
    f.dep_delay_minutes,
    f.dep_del15,
    f.arr_delay,
    f.arr_delay_minutes,
    f.arr_del15,
    -- The industry convention (DOT A14) counts a flight on time if it arrives
    -- fewer than 15 minutes after schedule. Cancelled and diverted flights are
    -- NOT on time, and are NOT excluded -- dropping them is how an airline that
    -- cancels its way out of a bad day appears to have had a good one.
    CASE WHEN f.cancelled OR f.diverted THEN FALSE
         ELSE f.arr_delay < 15 END                  AS is_on_time_a14,

    f.taxi_out,
    f.taxi_in,
    f.crs_elapsed_time,
    f.actual_elapsed_time,
    f.air_time,
    -- Negative means the schedule held more block time than the flight used:
    -- padding. Positive means the schedule was optimistic.
    f.actual_elapsed_time - f.crs_elapsed_time      AS block_time_variance,
    f.distance_miles,
    f.distance_group,

    -- cause attribution, zero-filled only where BTS actually reported causes
    f.carrier_delay,
    f.weather_delay,
    f.nas_delay,
    f.security_delay,
    f.late_aircraft_delay,
    f.late_aircraft_delay IS NOT NULL               AS has_cause_attribution,
    -- 15 records in 60 months arrive 15+ minutes late, carry the cause fields,
    -- and report zero in all five of them -- a delay with no stated reason. The
    -- feed offers no way to recover what happened, so they are flagged and
    -- excluded from cause analysis rather than counted as a sixth cause.
    f.late_aircraft_delay IS NOT NULL
        AND greatest(f.carrier_delay, f.weather_delay, f.nas_delay,
                     f.security_delay, f.late_aircraft_delay) > 0
                                                    AS has_complete_attribution,

    coalesce(f.carrier_delay, 0)
        + coalesce(f.weather_delay, 0)
        + coalesce(f.nas_delay, 0)
        + coalesce(f.security_delay, 0)             AS root_delay_minutes,
    coalesce(f.late_aircraft_delay, 0)              AS inherited_delay_minutes,

    -- What the airline itself could have prevented on this leg, as opposed to
    -- weather and airspace constraints it could only absorb.
    coalesce(f.carrier_delay, 0)                    AS controllable_root_minutes,
    coalesce(f.weather_delay, 0)
        + coalesce(f.nas_delay, 0)
        + coalesce(f.security_delay, 0)             AS external_root_minutes,

    -- The dominant reported cause, for slicing. Ties resolve toward the
    -- addressable cause rather than the convenient one.
    CASE
        WHEN f.late_aircraft_delay IS NULL          THEN NULL
        WHEN greatest(f.carrier_delay, f.weather_delay, f.nas_delay,
                      f.security_delay, f.late_aircraft_delay) = 0 THEN 'None reported'
        WHEN f.carrier_delay >= greatest(f.weather_delay, f.nas_delay,
                                         f.security_delay, f.late_aircraft_delay) THEN 'Carrier'
        WHEN f.late_aircraft_delay >= greatest(f.weather_delay, f.nas_delay,
                                               f.security_delay)  THEN 'Late aircraft'
        WHEN f.nas_delay >= greatest(f.weather_delay, f.security_delay) THEN 'National Air System'
        WHEN f.weather_delay >= f.security_delay    THEN 'Weather'
        ELSE 'Security'
    END                                             AS primary_cause
FROM stg_flight f;

-- Aircraft rotations: chain each airframe's legs into the sequence it actually
-- flew, so that a delay can be followed from the leg that caused it to the legs
-- that inherited it.
--
-- HOW THE CHAIN IS BUILT
--
-- Order every completed leg by tail number and scheduled departure instant.
-- Two consecutive legs belong to the same rotation when the previous leg landed
-- where this one departs, and the gap between them is short enough to be a turn
-- rather than an overnight sit or a maintenance visit.
--
-- The airport-match condition is what makes this trustworthy. Tail numbers are
-- reassigned between operators, ferry and maintenance flights are missing from
-- the passenger feed, and a cancelled leg leaves a hole. Every one of those
-- shows up as prev_dest <> origin and is excluded rather than silently treated
-- as a turn.
--
-- MAX_TURN_MINUTES = 720 (12 hours). Above that the aircraft has sat overnight
-- and any inbound delay has been fully absorbed; there is nothing left to
-- propagate. The threshold is a judgement call, and the sensitivity of the
-- headline propagation numbers to it is reported in the analysis.

CREATE OR REPLACE TABLE int_rotation_leg AS
WITH flyable AS (
    SELECT *
    FROM fct_flight
    WHERE completed
      AND tail_number IS NOT NULL
      -- Placeholder tails in the feed: 'UNKNOW', '-N/A-', 'N/A', 000000 and
      -- friends. Real US registrations are N + 1-5 alphanumerics.
      AND regexp_matches(tail_number, '^N[0-9][0-9A-Z]{1,4}$')
      AND actual_arr_utc IS NOT NULL
      AND actual_dep_utc IS NOT NULL
),

sequenced AS (
    SELECT
        *,
        row_number() OVER w                    AS leg_seq,
        lag(dest)           OVER w             AS prev_dest,
        lag(carrier)        OVER w             AS prev_carrier,
        lag(flight_date)    OVER w             AS prev_flight_date,
        lag(flight_number)  OVER w             AS prev_flight_number,
        lag(origin)         OVER w             AS prev_origin,
        lag(sched_arr_utc)  OVER w             AS prev_sched_arr_utc,
        lag(actual_arr_utc) OVER w             AS prev_actual_arr_utc,
        lag(arr_delay)      OVER w             AS prev_arr_delay,
        lag(root_delay_minutes)     OVER w     AS prev_root_delay_minutes,
        lag(inherited_delay_minutes) OVER w    AS prev_inherited_delay_minutes,
        lag(primary_cause)  OVER w             AS prev_primary_cause
    FROM flyable
    WINDOW w AS (PARTITION BY tail_number ORDER BY sched_dep_utc)
)

SELECT
    *,
    datediff('minute', prev_sched_arr_utc,  sched_dep_utc) AS sched_turn_minutes,
    datediff('minute', prev_actual_arr_utc, actual_dep_utc) AS actual_turn_minutes,
    (
        prev_dest = origin
        AND prev_sched_arr_utc IS NOT NULL
        AND datediff('minute', prev_sched_arr_utc, sched_dep_utc) BETWEEN 0 AND 720
    )                                                      AS is_continuation
FROM sequenced;

-- Rotation fact: every leg, with the slack it had and the delay it inherited.
--
-- THE PROPAGATION MODEL
--
-- When an aircraft lands late, the next departure is late only by the amount
-- the turn could not absorb:
--
--     slack              = scheduled_turn - minimum_feasible_turn
--     predicted_inherited = max(0, inbound_arrival_delay - slack)
--
-- This is a one-line model, and its value is that it can be CHECKED. BTS asks
-- airlines to report how many minutes of each delay were caused by a late
-- inbound aircraft, so the feed already contains the answer the model is trying
-- to predict. Agreement means the mechanism is real; disagreement localises
-- where schedules, not aircraft, are the problem.
--
-- CASCADE CHAINS
--
-- A cascade is a run of consecutive legs each inheriting delay from the last.
-- Islands are found with the standard gaps-and-islands pattern: a running sum
-- of "this leg is NOT inheriting" gives every chain a stable id, so the first
-- leg of each chain is its root and everything after it is downstream damage
-- traceable to that single root event.

CREATE OR REPLACE TABLE fct_rotation_leg AS
WITH with_slack AS (
    SELECT
        l.*,
        t.min_turn_minutes,
        t.benchmark_level,
        greatest(l.sched_turn_minutes - t.min_turn_minutes, 0)  AS turn_slack_minutes,
        CASE WHEN l.is_continuation AND l.prev_arr_delay > 0
             THEN greatest(l.prev_arr_delay
                           - greatest(l.sched_turn_minutes - t.min_turn_minutes, 0), 0)
             ELSE 0
        END                                                     AS predicted_inherited_minutes
    FROM int_rotation_leg l
    LEFT JOIN ref_min_turn t
           ON t.carrier = l.carrier AND t.airport = l.origin
),

chained AS (
    SELECT
        *,
        -- A leg continues a cascade when it is a genuine turn AND the airline
        -- attributed some of its delay to the late inbound aircraft.
        (is_continuation AND inherited_delay_minutes > 0)       AS is_inheriting,
        sum(CASE WHEN is_continuation AND inherited_delay_minutes > 0 THEN 0 ELSE 1 END)
            OVER (PARTITION BY tail_number ORDER BY sched_dep_utc
                  ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS cascade_id
    FROM with_slack
)

SELECT
    *,
    -- Position within the cascade: 0 is the root leg, 1 is the first leg to
    -- inherit from it, and so on down the day.
    row_number() OVER (PARTITION BY tail_number, cascade_id ORDER BY sched_dep_utc) - 1
        AS cascade_position,
    count(*) OVER (PARTITION BY tail_number, cascade_id) - 1
        AS cascade_length,
    -- Model error, the number the validation section is about. Positive means
    -- the airline attributed more to the late inbound than the slack arithmetic
    -- can account for.
    inherited_delay_minutes - predicted_inherited_minutes
        AS inherited_prediction_error
FROM chained;

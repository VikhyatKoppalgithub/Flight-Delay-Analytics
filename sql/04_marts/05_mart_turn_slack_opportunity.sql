-- Where to add schedule buffer, ranked. This is the deliverable the analysis
-- exists to produce.
--
-- THE SIMULATION
--
-- For every real turn in the window, the propagation model says the delay
-- handed to the next leg is:
--
--     max(0, inbound_delay - slack)
--
-- Re-running that with slack + N gives the delay that WOULD have been handed on
-- had the schedule held N more minutes of ground time at that station. The
-- difference is minutes of delay avoided.
--
-- THE TRADE-OFF, STATED HONESTLY
--
-- Buffer is not free: every added minute is paid on every turn, including the
-- overwhelming majority that were never going to be late. So the ranking metric
-- is not minutes saved -- it is minutes saved per buffer minute spent:
--
--     efficiency = delay_minutes_avoided / (N * turns_affected)
--
-- Above 1.0, the buffer returns more delay reduction than the schedule time it
-- consumes. Below it, the station is being asked to insure against a risk it
-- does not have.
--
-- WHAT THIS DOES NOT COST
--
-- Aircraft utilisation. Ground time an airframe spends parked is time it is not
-- earning, and the fleet-planning cost of that is not in this feed. So this
-- table ranks candidates and sizes the delay benefit; it does not claim a net
-- P&L number. That boundary is deliberate.

CREATE OR REPLACE TABLE mart_turn_slack_opportunity AS
WITH turns AS (
    SELECT
        r.carrier,
        r.origin                                AS airport_code,
        r.turn_slack_minutes,
        r.sched_turn_minutes,
        r.min_turn_minutes,
        coalesce(r.prev_arr_delay, 0)           AS inbound_delay,
        r.inherited_delay_minutes,
        r.benchmark_level
    FROM fct_rotation_leg r
    WHERE r.is_continuation
),

simulated AS (
    SELECT
        carrier,
        airport_code,
        count(*)                                                    AS turns,
        round(median(sched_turn_minutes), 0)                        AS median_sched_turn_minutes,
        round(median(min_turn_minutes), 0)                          AS min_feasible_turn_minutes,
        round(median(turn_slack_minutes), 0)                        AS median_slack_minutes,
        round(100.0 * avg((turn_slack_minutes < 15)::INT), 1)        AS tight_turn_pct,
        sum(inherited_delay_minutes)                                AS actual_inherited_minutes,

        sum(greatest(inbound_delay - turn_slack_minutes, 0))         AS predicted_base,
        sum(greatest(inbound_delay - (turn_slack_minutes + 5), 0))   AS predicted_plus_5,
        sum(greatest(inbound_delay - (turn_slack_minutes + 10), 0))  AS predicted_plus_10,
        sum(greatest(inbound_delay - (turn_slack_minutes + 15), 0))  AS predicted_plus_15,
        max(benchmark_level)                                        AS benchmark_level
    FROM turns
    GROUP BY carrier, airport_code
),

costed AS (
    SELECT
        s.*,
        predicted_base - predicted_plus_5   AS minutes_saved_plus_5,
        predicted_base - predicted_plus_10  AS minutes_saved_plus_10,
        predicted_base - predicted_plus_15  AS minutes_saved_plus_15,
        (predicted_base - predicted_plus_10) / nullif(10.0 * turns, 0)  AS efficiency_plus_10
    FROM simulated s
)

SELECT
    c.carrier,
    d.carrier_name,
    c.airport_code,
    a.city,
    a.size_band,
    c.turns,
    c.median_sched_turn_minutes,
    c.min_feasible_turn_minutes,
    c.median_slack_minutes,
    c.tight_turn_pct,
    c.actual_inherited_minutes,
    c.minutes_saved_plus_5,
    c.minutes_saved_plus_10,
    c.minutes_saved_plus_15,
    round(c.efficiency_plus_10, 3)                                  AS efficiency_plus_10,
    round(c.minutes_saved_plus_10
          * (SELECT value FROM ref_cost_assumption WHERE assumption = 'block_minute_usd'), 0)
                                                                    AS delay_cost_avoided_usd_plus_10,
    c.benchmark_level
FROM costed c
LEFT JOIN dim_carrier d ON d.carrier = c.carrier
LEFT JOIN dim_airport a ON a.airport_code = c.airport_code
-- Below ~2,000 turns over five years the station sees roughly one turn a day and
-- the percentiles behind min_feasible_turn are not stable enough to schedule on.
WHERE c.turns >= 2000
ORDER BY c.minutes_saved_plus_10 DESC;

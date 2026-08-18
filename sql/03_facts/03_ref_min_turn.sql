-- Minimum feasible turn time, measured rather than assumed.
--
-- To know whether a schedule had enough slack to absorb an inbound delay, we
-- need to know how fast the aircraft COULD have been turned. Published minimum
-- turn times are not in this dataset, so they are inferred from behaviour: the
-- 5th percentile of turns the operator actually achieved at that airport. That
-- is the floor they hit when they were pushing, which is the relevant benchmark
-- for asking whether a schedule left room.
--
-- Falls back carrier-wide, then network-wide, wherever the sample is thin.
-- MIN_SAMPLE = 100 turns; below that a 5th percentile is noise.

CREATE OR REPLACE TABLE ref_min_turn AS
WITH turns AS (
    SELECT carrier, origin AS airport, actual_turn_minutes
    FROM int_rotation_leg
    WHERE is_continuation
      AND actual_turn_minutes > 0
      AND actual_turn_minutes <= 720
),

by_carrier_airport AS (
    SELECT carrier, airport,
           quantile_cont(actual_turn_minutes, 0.05) AS p05_turn,
           count(*)                                 AS n
    FROM turns GROUP BY carrier, airport
),
by_carrier AS (
    SELECT carrier,
           quantile_cont(actual_turn_minutes, 0.05) AS p05_turn,
           count(*)                                 AS n
    FROM turns GROUP BY carrier
),
network AS (
    SELECT quantile_cont(actual_turn_minutes, 0.05) AS p05_turn FROM turns
)

SELECT
    ca.carrier,
    ca.airport,
    ca.n                                           AS sample_size,
    CASE
        WHEN ca.n >= 100 THEN ca.p05_turn
        WHEN c.n  >= 100 THEN c.p05_turn
        ELSE (SELECT p05_turn FROM network)
    END                                            AS min_turn_minutes,
    CASE
        WHEN ca.n >= 100 THEN 'carrier_airport'
        WHEN c.n  >= 100 THEN 'carrier'
        ELSE 'network'
    END                                            AS benchmark_level
FROM by_carrier_airport ca
LEFT JOIN by_carrier c USING (carrier);

-- One row per cascade: a root delay and everything it went on to break.
--
-- This is the table that answers "what did that delay actually cost?", as
-- opposed to "how late was that flight?". The root leg is the one that started
-- late for a reason of its own; the downstream legs are the ones that were late
-- because the aircraft was.
--
-- Cascades of length zero (a delay that ended where it started) are kept, so
-- the denominator is every root delay rather than only the damaging ones.

CREATE OR REPLACE TABLE mart_cascade AS
WITH roots AS (
    SELECT
        tail_number,
        cascade_id,
        carrier,
        flight_date,
        origin                              AS root_origin,
        dest                                AS root_dest,
        sched_dep_utc                       AS root_sched_dep_utc,
        sched_dep_hour_local                AS root_dep_hour_local,
        arr_delay                           AS root_arr_delay,
        root_delay_minutes                  AS root_delay_minutes,
        controllable_root_minutes           AS root_controllable_minutes,
        external_root_minutes               AS root_external_minutes,
        primary_cause                       AS root_primary_cause
    FROM fct_rotation_leg
    WHERE cascade_position = 0
),

downstream AS (
    SELECT
        tail_number,
        cascade_id,
        count(*)                            AS downstream_legs,
        sum(inherited_delay_minutes)        AS downstream_delay_minutes,
        sum(arr_delay)                      AS downstream_arr_delay_minutes,
        max(cascade_position)               AS max_position,
        -- Airports that received a late aircraft because of this one root.
        count(DISTINCT dest)                AS downstream_stations_touched
    FROM fct_rotation_leg
    WHERE cascade_position > 0
    GROUP BY tail_number, cascade_id
)

SELECT
    r.*,
    d.carrier_name,
    d.carrier_type,
    coalesce(ds.downstream_legs, 0)                 AS downstream_legs,
    coalesce(ds.downstream_delay_minutes, 0)        AS downstream_delay_minutes,
    coalesce(ds.downstream_stations_touched, 0)     AS downstream_stations_touched,
    r.root_delay_minutes
        + coalesce(ds.downstream_delay_minutes, 0)  AS total_cascade_minutes,
    -- Amplification: for every minute the root flight lost, how many minutes did
    -- the network lose in total? A value of 3 means the delay tripled on its way
    -- through the day.
    round((r.root_delay_minutes + coalesce(ds.downstream_delay_minutes, 0))
          / nullif(r.root_delay_minutes, 0), 2)     AS amplification_ratio,
    (r.root_delay_minutes + coalesce(ds.downstream_delay_minutes, 0))
        * (SELECT value FROM ref_cost_assumption WHERE assumption = 'block_minute_usd')
                                                    AS total_cascade_cost_usd
FROM roots r
LEFT JOIN downstream ds USING (tail_number, cascade_id)
LEFT JOIN dim_carrier d ON d.carrier = r.carrier
WHERE r.root_delay_minutes > 0;

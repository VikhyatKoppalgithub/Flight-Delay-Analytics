-- Airport dimension, narrowed to airports that actually appear in the window
-- and enriched with a size band.
--
-- On the size band: the FAA classifies hubs by share of national passenger
-- ENPLANEMENTS (large >= 1%, medium 0.25-1%, small 0.05-0.25%). This dataset
-- has no passenger counts, so the band below is computed from share of
-- DEPARTURES using the same thresholds. It tracks the FAA categories closely
-- but is not identical -- an airport served mainly by regional jets shows a
-- higher departure share than its enplanement share. Named `size_band` rather
-- than `hub_category` so it is not mistaken for the official classification.

CREATE OR REPLACE TABLE dim_airport AS
WITH departures AS (
    SELECT origin AS airport_code, count(*) AS departures
    FROM stg_flight
    GROUP BY origin
),
arrivals AS (
    SELECT dest AS airport_code, count(*) AS arrivals
    FROM stg_flight
    GROUP BY dest
),
activity AS (
    SELECT
        coalesce(d.airport_code, a.airport_code) AS airport_code,
        coalesce(d.departures, 0)                AS departures,
        coalesce(a.arrivals, 0)                  AS arrivals
    FROM departures d
    FULL OUTER JOIN arrivals a USING (airport_code)
),
shares AS (
    SELECT *, departures / sum(departures) OVER () AS departure_share
    FROM activity
)

SELECT
    s.airport_code,
    ap.airport_name,
    ap.city,
    ap.country,
    ap.latitude,
    ap.longitude,
    ap.timezone,
    s.departures,
    s.arrivals,
    s.departure_share,
    CASE
        WHEN s.departure_share >= 0.0100 THEN 'Large'
        WHEN s.departure_share >= 0.0025 THEN 'Medium'
        WHEN s.departure_share >= 0.0005 THEN 'Small'
        ELSE 'Non-hub'
    END AS size_band,
    ap.airport_code IS NOT NULL AS is_mapped
FROM shares s
LEFT JOIN stg_airport ap USING (airport_code)
ORDER BY s.departures DESC;

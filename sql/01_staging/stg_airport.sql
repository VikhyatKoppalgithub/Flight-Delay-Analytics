-- Airport reference data.
--
-- The BTS feed identifies airports by IATA code and carries city/state, but no
-- coordinates and -- more importantly -- no timezone. Without a timezone every
-- clock field in the feed is a local time that cannot be compared across
-- airports, which makes turn times and delay propagation impossible to compute
-- correctly. OpenFlights supplies the IANA timezone name, which DuckDB's ICU
-- extension can apply including daylight saving transitions.
--
-- Source: https://github.com/jpatokal/openflights (airports.dat, public domain)

CREATE OR REPLACE TABLE stg_airport AS
WITH openflights AS (
    SELECT
        c04                     AS airport_code,
        c01                     AS airport_name,
        c02                     AS city,
        c03                     AS country,
        TRY_CAST(c06 AS DOUBLE) AS latitude,
        TRY_CAST(c07 AS DOUBLE) AS longitude,
        nullif(c11, '\N')       AS timezone
    FROM read_csv(
        '${DATA_RAW}/openflights_airports.dat',
        header = false,
        columns = {
            'c00':'VARCHAR','c01':'VARCHAR','c02':'VARCHAR','c03':'VARCHAR',
            'c04':'VARCHAR','c05':'VARCHAR','c06':'VARCHAR','c07':'VARCHAR',
            'c08':'VARCHAR','c09':'VARCHAR','c10':'VARCHAR','c11':'VARCHAR',
            'c12':'VARCHAR','c13':'VARCHAR'
        }
    )
    WHERE c04 IS NOT NULL
      AND c04 <> '\N'
      AND length(c04) = 3
),

-- OpenFlights stopped taking updates before these opened or were recoded.
-- Every code here was found by the unmatched-airport test in tests/, not
-- guessed: run the pipeline, read the failure, add the row.
overrides(airport_code, airport_name, city, country, latitude, longitude, timezone) AS (
    VALUES
        -- Opened 2019, after OpenFlights stopped taking updates.
        ('XWA', 'Williston Basin International Airport', 'Williston',
         'United States', 48.2581, -103.7486, 'America/Chicago'),
        -- Present in OpenFlights but with a null timezone.
        ('BIH', 'Eastern Sierra Regional Airport', 'Bishop',
         'United States', 37.3731, -118.3636, 'America/Los_Angeles'),
        -- Absent from OpenFlights entirely.
        ('EAR', 'Kearney Regional Airport', 'Kearney',
         'United States', 40.7270, -99.0068, 'America/Chicago'),
        -- Arizona: no daylight saving, which is exactly the kind of detail that
        -- silently shifts an hour of turn time if the timezone is guessed.
        ('IFP', 'Laughlin/Bullhead International Airport', 'Bullhead City',
         'United States', 35.1574, -114.5595, 'America/Phoenix')
)

SELECT * FROM overrides
UNION ALL
SELECT o.* FROM openflights o
WHERE o.airport_code NOT IN (SELECT airport_code FROM overrides);

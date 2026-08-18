-- Calendar dimension for the analysis window.
--
-- Two things make this worth materialising rather than deriving inline.
--
-- First, holidays. US federal holidays move; hardcoding the eleven rules below
-- as resolved dates keeps them auditable (each row carries the rule it came
-- from) without a Python dependency in the SQL layer.
--
-- Second, and more useful analytically: the holiday DATE is rarely the day
-- operations break. Thanksgiving Day itself is one of the quietest flying days
-- of the year -- the load is on the Tuesday and Wednesday before it and the
-- Sunday after. The travel-period flags below capture the window that actually
-- stresses the network, which is what the demand and delay analysis keys on.

CREATE OR REPLACE TABLE dim_date AS
WITH calendar AS (
    SELECT unnest(generate_series(DATE '2021-01-01', DATE '2025-12-31', INTERVAL 1 DAY))::DATE AS date_day
),

federal_holiday(date_day, holiday_name, rule) AS (
    VALUES
        (DATE '2021-01-01', 'New Year''s Day'            , 'Jan 1'),
        (DATE '2021-01-18', 'Martin Luther King Jr. Day', '3rd Monday of January'),
        (DATE '2021-02-15', 'Presidents'' Day'           , '3rd Monday of February'),
        (DATE '2021-05-31', 'Memorial Day'              , 'Last Monday of May'),
        (DATE '2021-06-19', 'Juneteenth'                , 'Jun 19'),
        (DATE '2021-07-04', 'Independence Day'          , 'Jul 4'),
        (DATE '2021-09-06', 'Labor Day'                 , '1st Monday of September'),
        (DATE '2021-10-11', 'Columbus Day'              , '2nd Monday of October'),
        (DATE '2021-11-11', 'Veterans Day'              , 'Nov 11'),
        (DATE '2021-11-25', 'Thanksgiving'              , '4th Thursday of November'),
        (DATE '2021-12-25', 'Christmas Day'             , 'Dec 25'),
        (DATE '2022-01-01', 'New Year''s Day'            , 'Jan 1'),
        (DATE '2022-01-17', 'Martin Luther King Jr. Day', '3rd Monday of January'),
        (DATE '2022-02-21', 'Presidents'' Day'           , '3rd Monday of February'),
        (DATE '2022-05-30', 'Memorial Day'              , 'Last Monday of May'),
        (DATE '2022-06-19', 'Juneteenth'                , 'Jun 19'),
        (DATE '2022-07-04', 'Independence Day'          , 'Jul 4'),
        (DATE '2022-09-05', 'Labor Day'                 , '1st Monday of September'),
        (DATE '2022-10-10', 'Columbus Day'              , '2nd Monday of October'),
        (DATE '2022-11-11', 'Veterans Day'              , 'Nov 11'),
        (DATE '2022-11-24', 'Thanksgiving'              , '4th Thursday of November'),
        (DATE '2022-12-25', 'Christmas Day'             , 'Dec 25'),
        (DATE '2023-01-01', 'New Year''s Day'            , 'Jan 1'),
        (DATE '2023-01-16', 'Martin Luther King Jr. Day', '3rd Monday of January'),
        (DATE '2023-02-20', 'Presidents'' Day'           , '3rd Monday of February'),
        (DATE '2023-05-29', 'Memorial Day'              , 'Last Monday of May'),
        (DATE '2023-06-19', 'Juneteenth'                , 'Jun 19'),
        (DATE '2023-07-04', 'Independence Day'          , 'Jul 4'),
        (DATE '2023-09-04', 'Labor Day'                 , '1st Monday of September'),
        (DATE '2023-10-09', 'Columbus Day'              , '2nd Monday of October'),
        (DATE '2023-11-11', 'Veterans Day'              , 'Nov 11'),
        (DATE '2023-11-23', 'Thanksgiving'              , '4th Thursday of November'),
        (DATE '2023-12-25', 'Christmas Day'             , 'Dec 25'),
        (DATE '2024-01-01', 'New Year''s Day'            , 'Jan 1'),
        (DATE '2024-01-15', 'Martin Luther King Jr. Day', '3rd Monday of January'),
        (DATE '2024-02-19', 'Presidents'' Day'           , '3rd Monday of February'),
        (DATE '2024-05-27', 'Memorial Day'              , 'Last Monday of May'),
        (DATE '2024-06-19', 'Juneteenth'                , 'Jun 19'),
        (DATE '2024-07-04', 'Independence Day'          , 'Jul 4'),
        (DATE '2024-09-02', 'Labor Day'                 , '1st Monday of September'),
        (DATE '2024-10-14', 'Columbus Day'              , '2nd Monday of October'),
        (DATE '2024-11-11', 'Veterans Day'              , 'Nov 11'),
        (DATE '2024-11-28', 'Thanksgiving'              , '4th Thursday of November'),
        (DATE '2024-12-25', 'Christmas Day'             , 'Dec 25'),
        (DATE '2025-01-01', 'New Year''s Day'            , 'Jan 1'),
        (DATE '2025-01-20', 'Martin Luther King Jr. Day', '3rd Monday of January'),
        (DATE '2025-02-17', 'Presidents'' Day'           , '3rd Monday of February'),
        (DATE '2025-05-26', 'Memorial Day'              , 'Last Monday of May'),
        (DATE '2025-06-19', 'Juneteenth'                , 'Jun 19'),
        (DATE '2025-07-04', 'Independence Day'          , 'Jul 4'),
        (DATE '2025-09-01', 'Labor Day'                 , '1st Monday of September'),
        (DATE '2025-10-13', 'Columbus Day'              , '2nd Monday of October'),
        (DATE '2025-11-11', 'Veterans Day'              , 'Nov 11'),
        (DATE '2025-11-27', 'Thanksgiving'              , '4th Thursday of November'),
        (DATE '2025-12-25', 'Christmas Day'             , 'Dec 25')
),

thanksgiving_window(window_start, window_end, label) AS (
    VALUES
        (DATE '2021-11-23', DATE '2021-11-29', 'Thanksgiving'),
        (DATE '2022-11-22', DATE '2022-11-28', 'Thanksgiving'),
        (DATE '2023-11-21', DATE '2023-11-27', 'Thanksgiving'),
        (DATE '2024-11-26', DATE '2024-12-02', 'Thanksgiving'),
        (DATE '2025-11-25', DATE '2025-12-01', 'Thanksgiving')
)

SELECT
    c.date_day,
    year(c.date_day)                                        AS year,
    quarter(c.date_day)                                     AS quarter,
    month(c.date_day)                                       AS month,
    monthname(c.date_day)                                   AS month_name,
    day(c.date_day)                                         AS day_of_month,
    isodow(c.date_day)                                      AS iso_day_of_week,
    dayname(c.date_day)                                     AS day_name,
    isodow(c.date_day) >= 6                                 AS is_weekend,
    h.holiday_name,
    h.holiday_name IS NOT NULL                              AS is_federal_holiday,
    CASE
        WHEN t.label IS NOT NULL                                    THEN 'Thanksgiving'
        WHEN (month(c.date_day) = 12 AND day(c.date_day) >= 20)
          OR (month(c.date_day) = 1  AND day(c.date_day) <= 3)      THEN 'Christmas / New Year'
        WHEN c.date_day BETWEEN
                 DATE_TRUNC('year', c.date_day) + INTERVAL 150 DAY
             AND DATE_TRUNC('year', c.date_day) + INTERVAL 248 DAY  THEN 'Summer peak'
        ELSE NULL
    END                                                     AS travel_period
FROM calendar c
LEFT JOIN federal_holiday h USING (date_day)
LEFT JOIN thanksgiving_window t
       ON c.date_day BETWEEN t.window_start AND t.window_end;

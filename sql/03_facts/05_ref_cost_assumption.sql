-- Cost assumptions, kept in one auditable table instead of scattered literals.
--
-- Airlines for America publishes the average direct cost of one minute of
-- aircraft block time for US passenger carriers, built from DOT Form 41
-- filings: crew, fuel, maintenance, aircraft ownership and other direct costs.
-- Published values:
--
--     2025   $98.41 / block minute   (labour $37.01, fuel $29.34)
--     2024   $100.76 / block minute
--
-- Source: https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/
--
-- ONE RATE IS APPLIED TO ALL FIVE YEARS, deliberately. Using each year's own
-- rate would mix a change in operational performance with a change in the price
-- of jet fuel, and the question here is whether the operation got better or
-- worse -- not whether fuel got cheaper. Holding the rate constant puts every
-- year in 2025 dollars so the comparison is about minutes, not markets. Swap in
-- year-specific rates below if the question changes.
--
-- What this cost does NOT include: passenger time, missed connections,
-- rebooking, compensation, crew rest cascades, or lost future bookings. A4A
-- estimates passenger time cost separately and it is of comparable size, so
-- every dollar figure in this project should be read as a LOWER BOUND on the
-- cost of delay, not an estimate of it.

CREATE OR REPLACE TABLE ref_cost_assumption AS
SELECT * FROM (VALUES
    ('block_minute_usd', 98.41,
     'A4A 2025 average direct cost per aircraft block minute, applied to all years',
     'https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/'),
    ('block_minute_usd_2024', 100.76,
     'A4A 2024 average, retained for sensitivity checks',
     'https://www.airlines.org/dataset/u-s-passenger-carrier-delay-costs/')
) AS t(assumption, value, note, source);

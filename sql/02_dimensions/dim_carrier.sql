-- Carrier dimension.
--
-- The single most misread field in this dataset. BTS reports the OPERATING
-- carrier, not the marketing carrier. A passenger who books "United 4801" and
-- flies a CRJ-900 operated by Republic Airways appears here as YX, not UA.
-- Roughly a third of US domestic departures are flown this way.
--
-- Consequences that matter for the analysis:
--   * Ranking carriers by on-time rate without accounting for this compares
--     network airlines against their own subcontractors.
--   * Regional operators fly shorter stages into smaller airports with tighter
--     turns, so their delay profile is structurally different, not just worse.
--   * A network airline's true customer-facing reliability requires rolling its
--     regional partners back up -- which this dataset cannot do exactly, since
--     SkyWest alone flies for four different brands. That limitation is stated
--     rather than papered over.
--
-- Source for names and affiliations: BTS carrier lookup (L_UNIQUE_CARRIERS)
-- and each operator's published capacity purchase agreements.

CREATE OR REPLACE TABLE dim_carrier AS
WITH lookup(carrier, carrier_name, carrier_type, operates_for) AS (
    VALUES
        -- Network carriers: hub-and-spoke, global alliances, own regional feed
        ('AA', 'American Airlines',   'Network',        NULL),
        ('DL', 'Delta Air Lines',     'Network',        NULL),
        ('UA', 'United Airlines',     'Network',        NULL),
        ('AS', 'Alaska Airlines',     'Network',        NULL),
        ('HA', 'Hawaiian Airlines',   'Network',        NULL),

        -- Low-cost: point-to-point, single fleet type, no regional feed
        ('WN', 'Southwest Airlines',  'Low-cost',       NULL),
        ('B6', 'JetBlue Airways',     'Low-cost',       NULL),
        ('SY', 'Sun Country Airlines','Low-cost',       NULL),
        ('MX', 'Breeze Airways',      'Low-cost',       NULL),

        -- Ultra low-cost: unbundled fares, high utilisation, thin turn buffers
        ('NK', 'Spirit Airlines',     'Ultra low-cost', NULL),
        ('F9', 'Frontier Airlines',   'Ultra low-cost', NULL),
        ('G4', 'Allegiant Air',       'Ultra low-cost', NULL),

        -- Regional: fly under a network brand on capacity purchase agreements
        ('OO', 'SkyWest Airlines',    'Regional',       'AA / DL / UA / AS'),
        ('YX', 'Republic Airways',    'Regional',       'AA / DL / UA'),
        ('MQ', 'Envoy Air',           'Regional',       'AA'),
        ('OH', 'PSA Airlines',        'Regional',       'AA'),
        ('PT', 'Piedmont Airlines',   'Regional',       'AA'),
        ('9E', 'Endeavor Air',        'Regional',       'DL'),
        ('YV', 'Mesa Airlines',       'Regional',       'AA / UA'),
        ('ZW', 'Air Wisconsin',       'Regional',       'AA / UA'),
        ('C5', 'CommuteAir',          'Regional',       'UA'),
        ('G7', 'GoJet Airlines',      'Regional',       'UA'),
        ('QX', 'Horizon Air',         'Regional',       'AS'),
        ('EV', 'ExpressJet Airlines', 'Regional',       'UA'),
        ('AX', 'Trans States Airlines','Regional',      'UA'),
        ('9K', 'Cape Air',            'Regional',       'Independent / EAS'),
        ('KS', 'PenAir',              'Regional',       'Independent / EAS'),
        ('EM', 'Empire Airlines',     'Regional',       'Independent')
),

observed AS (
    SELECT carrier, count(*) AS flights, min(flight_date) AS first_seen, max(flight_date) AS last_seen
    FROM stg_flight
    GROUP BY carrier
)

SELECT
    o.carrier,
    coalesce(l.carrier_name, 'UNKNOWN (' || o.carrier || ')') AS carrier_name,
    coalesce(l.carrier_type, 'Unknown')                       AS carrier_type,
    l.operates_for,
    l.carrier IS NOT NULL                                     AS is_mapped,
    o.flights,
    o.first_seen,
    o.last_seen
FROM observed o
LEFT JOIN lookup l USING (carrier)
ORDER BY o.flights DESC;

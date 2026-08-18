"""Data quality tests.

These are assertions about the warehouse, not about the code that built it. Each
one encodes something that must be true if the model is right, and several of
them have caught real problems: the missing-timezone airports and the placeholder
tail numbers were both found here rather than by reading output.
"""

import pytest


# ---------------------------------------------------------------- completeness

def test_every_month_in_the_window_is_present(scalar):
    """60 months, 2021-01 through 2025-12, no holes."""
    assert scalar("SELECT count(DISTINCT (year, month)) FROM fct_flight") == 60


def test_flight_volume_is_plausible(scalar):
    """US domestic scheduled service runs 6-8M flights a year."""
    per_year = scalar("SELECT count(*) / count(DISTINCT year) FROM fct_flight")
    assert 5_000_000 < per_year < 9_000_000


def test_no_duplicate_flight_legs(scalar):
    dupes = scalar("""
        SELECT count(*) FROM (
            SELECT flight_date, carrier, flight_number, origin, dest, crs_dep_time
            FROM fct_flight
            GROUP BY ALL HAVING count(*) > 1
        )
    """)
    assert dupes == 0


# ------------------------------------------------------------------- reference

def test_every_airport_resolves_to_reference_data(con):
    """An unmapped airport means a NULL timezone, which silently corrupts every
    UTC timestamp downstream. Failures list the codes to add to the overrides
    block in stg_airport.sql."""
    missing = con.execute("""
        SELECT airport_code, departures FROM dim_airport
        WHERE NOT is_mapped OR timezone IS NULL ORDER BY departures DESC
    """).fetchall()
    assert missing == [], f"add to stg_airport.sql overrides: {missing}"


def test_every_carrier_is_named(con):
    unmapped = con.execute(
        "SELECT carrier, flights FROM dim_carrier WHERE NOT is_mapped ORDER BY flights DESC"
    ).fetchall()
    assert unmapped == [], f"add to dim_carrier.sql lookup: {unmapped}"


def test_date_dimension_has_no_gaps(scalar):
    assert scalar("SELECT count(*) FROM dim_date") == 1826  # 2021-2025, one leap year


# -------------------------------------------------------------- BTS invariants

def test_delay_causes_sum_to_arrival_delay(scalar):
    """BTS specifies that the five cause fields partition ArrDelayMinutes
    exactly. If this drifts, the ingest cast is losing minutes."""
    violations = scalar("""
        SELECT count(*) FROM fct_flight
        WHERE has_complete_attribution
          AND abs((carrier_delay + weather_delay + nas_delay
                   + security_delay + late_aircraft_delay) - arr_delay_minutes) > 1
    """)
    assert violations == 0


def test_delays_filed_without_a_reason_stay_negligible(scalar):
    """The known feed defect: late flights whose five cause fields are all zero.
    15 records in 60 months. Pinned so that if a future month arrives with
    thousands of them, the analysis notices instead of quietly absorbing it."""
    unexplained = scalar("""
        SELECT count(*) FROM fct_flight
        WHERE has_cause_attribution AND NOT has_complete_attribution
    """)
    attributed = scalar("SELECT count(*) FROM fct_flight WHERE has_cause_attribution")
    assert unexplained / attributed < 0.0001


def test_cause_attribution_appears_only_on_delayed_flights(scalar):
    """BTS populates causes only at 15+ minutes late. A flight with attribution
    and a sub-15 delay means the join or the filter is wrong."""
    assert scalar("""
        SELECT count(*) FROM fct_flight
        WHERE has_cause_attribution AND completed AND arr_delay < 15
    """) == 0


def test_root_and_inherited_partition_the_delay(scalar):
    assert scalar("""
        SELECT count(*) FROM fct_flight
        WHERE has_complete_attribution
          AND abs((root_delay_minutes + inherited_delay_minutes) - arr_delay_minutes) > 1
    """) == 0


# ------------------------------------------------------------------ timestamps

def test_scheduled_arrival_follows_scheduled_departure(scalar):
    """Guaranteed by construction once invalid schedules are excluded -- which
    is the point: the exclusion is what makes it guaranteed."""
    assert scalar("""
        SELECT count(*) FROM fct_flight
        WHERE sched_arr_utc IS NOT NULL AND sched_arr_utc <= sched_dep_utc
    """) == 0


def test_corrupt_schedules_are_flagged_not_dropped(scalar):
    """Records with a negative scheduled block time are kept and flagged, so the
    flight count still reconciles to the source, but derive no timestamps."""
    invalid = scalar("SELECT count(*) FROM fct_flight WHERE NOT is_schedule_valid")
    assert 0 < invalid < 100
    assert scalar("""
        SELECT count(*) FROM fct_flight WHERE NOT is_schedule_valid AND sched_arr_utc IS NOT NULL
    """) == 0


def test_actual_departure_matches_reported_delay(scalar):
    """actual_dep_utc is derived from sched_dep_utc + dep_delay, so this checks
    the timezone conversion did not shift anything."""
    assert scalar("""
        SELECT count(*) FROM fct_flight
        WHERE completed
          AND abs(datediff('minute', sched_dep_utc, actual_dep_utc) - dep_delay) > 0
    """) == 0


def test_daylight_saving_is_applied(scalar):
    """The same local clock time maps to different UTC instants either side of a
    DST transition. Chicago is UTC-6 in winter and UTC-5 in summer; if ICU were
    not loaded, or the session timezone were not pinned to UTC, this would not
    come out as exactly two offsets."""
    offsets = scalar("""
        SELECT count(DISTINCT datediff('hour', sched_dep_local, sched_dep_utc::TIMESTAMP))
        FROM fct_flight WHERE origin = 'ORD'
    """)
    assert offsets == 2  # CST and CDT


# ------------------------------------------------------------------- KPI logic

def test_cancelled_flights_are_never_on_time(scalar):
    assert scalar("""
        SELECT count(*) FROM fct_flight WHERE (cancelled OR diverted) AND is_on_time_a14
    """) == 0


def test_on_time_rate_is_in_a_believable_band(scalar):
    """US domestic A14 has run 72-83% since 2021. Outside that band something
    structural is wrong, not merely surprising."""
    rate = scalar("SELECT 100.0 * avg(is_on_time_a14::INT) FROM fct_flight")
    assert 70 < rate < 85


# -------------------------------------------------------------------- rotation

def test_continuations_are_physically_possible(scalar):
    """A turn requires the aircraft to already be at the airport it departs."""
    assert scalar("""
        SELECT count(*) FROM fct_rotation_leg
        WHERE is_continuation AND (prev_dest <> origin OR sched_turn_minutes < 0)
    """) == 0


def test_no_placeholder_tail_numbers_survive(scalar):
    assert scalar("""
        SELECT count(*) FROM fct_rotation_leg
        WHERE tail_number IN ('UNKNOW', 'N/A', '-N/A-', '000000', '')
    """) == 0


def test_every_cascade_has_exactly_one_root(scalar):
    assert scalar("""
        SELECT count(*) FROM (
            SELECT tail_number, cascade_id
            FROM fct_rotation_leg WHERE cascade_position = 0
            GROUP BY ALL HAVING count(*) <> 1
        )
    """) == 0


def test_propagation_model_tracks_reported_attribution(scalar):
    """The slack model predicts how much delay a turn hands on; BTS records what
    the airline said it handed on. These are independent, so agreement is
    evidence the mechanism is real. Guards against silent regression."""
    correlation = scalar("""
        SELECT corr(predicted_inherited_minutes, inherited_delay_minutes)
        FROM fct_rotation_leg
        WHERE is_continuation AND prev_arr_delay > 15
    """)
    assert correlation > 0.70


def test_slack_reduces_inherited_delay(scalar):
    """The core mechanism as an endpoint comparison: among turns receiving a
    comparably late aircraft, the least-slack bucket must pass on materially more
    delay than the most-slack bucket. Deliberately NOT a monotonicity check --
    the middle buckets are not monotonic, for reasons documented in Finding 2."""
    tight, loose = scalar("""
        SELECT [
            avg(inherited_delay_minutes) FILTER (WHERE turn_slack_minutes < 15),
            avg(inherited_delay_minutes) FILTER (WHERE turn_slack_minutes >= 60)
        ] FROM fct_rotation_leg
        WHERE is_continuation AND prev_arr_delay BETWEEN 30 AND 60
    """)
    assert tight > loose * 1.5


# ----------------------------------------------------------------------- marts

@pytest.mark.parametrize("table", [
    "mart_carrier_monthly", "mart_airport_daily", "mart_route_reliability",
    "mart_cascade", "mart_turn_slack_opportunity",
])
def test_mart_is_populated(scalar, table):
    assert scalar(f"SELECT count(*) FROM {table}") > 0


def test_carrier_monthly_reconciles_to_the_fact_table(scalar):
    assert scalar("""
        SELECT abs((SELECT sum(scheduled_flights) FROM mart_carrier_monthly)
                   - (SELECT count(*) FROM fct_flight))
    """) == 0


def test_percentages_are_percentages(con):
    for table, column in [
        ("mart_carrier_monthly", "on_time_arrival_pct"),
        ("mart_carrier_monthly", "completion_factor_pct"),
        ("mart_airport_daily", "cancellation_rate_pct"),
        ("mart_route_reliability", "on_time_arrival_pct"),
    ]:
        bad = con.execute(
            f"SELECT count(*) FROM {table} WHERE {column} < 0 OR {column} > 100"
        ).fetchone()[0]
        assert bad == 0, f"{table}.{column}"

"""Shared configuration for the ingestion pipeline.

The analysis window is 2021-01 through 2025-12 — five complete calendar years.

2020 is deliberately excluded. The pandemic collapse in traffic makes every
year-over-year comparison meaningless and would force a caveat onto every
chart. Starting at 2021 keeps two events that are genuinely useful instead:
the summer 2022 staffing meltdown and the December 2022 Southwest crew
scheduling collapse, both of which are used as natural experiments later.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PARQUET_DIR = ROOT / "data" / "parquet"
WAREHOUSE_DIR = ROOT / "data" / "warehouse"
WAREHOUSE = WAREHOUSE_DIR / "flights.duckdb"

START_YEAR, START_MONTH = 2021, 1
END_YEAR, END_MONTH = 2025, 12

BASE_URL = (
    "https://transtats.bts.gov/PREZIP/"
    "On_Time_Reporting_Carrier_On_Time_Performance_1987_present_{year}_{month}.zip"
)


def months(start=(START_YEAR, START_MONTH), end=(END_YEAR, END_MONTH)):
    """Yield (year, month) pairs across the inclusive window."""
    year, month = start
    while (year, month) <= end:
        yield year, month
        month += 1
        if month == 13:
            year, month = year + 1, 1


# The BTS extract carries 110 columns; 61 of them describe up to five
# diversion legs per flight and are empty for >99.9% of rows. Below is the
# subset the warehouse uses, with the target name and type for each.
#
# Types are declared rather than sniffed. DuckDB's CSV sniffer is reliable but
# it reads only a sample, and across 60 files a column that is all-empty in one
# month (SecurityDelay is close) can be typed differently than in the next.
# Declaring them keeps every parquet file union-compatible.
#
#   int      whole number
#   hhmm     local clock time as HHMM, e.g. 856 = 08:56, 2400 = midnight
#   minutes  duration in whole minutes, stored by BTS as "12.00"
#   num      other numeric measure (distance in statute miles)
#   bool     BTS 0.00/1.00 indicator
#   date     ISO date
#   str      text
SCHEMA = [
    # (source column, warehouse column, type)
    ("Year",                             "year",                 "int"),
    ("Quarter",                          "quarter",              "int"),
    ("Month",                            "month",                "int"),
    ("DayofMonth",                       "day_of_month",         "int"),
    ("DayOfWeek",                        "day_of_week",          "int"),
    ("FlightDate",                       "flight_date",          "date"),

    ("Reporting_Airline",                "carrier",              "str"),
    ("DOT_ID_Reporting_Airline",         "carrier_dot_id",       "int"),
    ("Tail_Number",                      "tail_number",          "str"),
    ("Flight_Number_Reporting_Airline",  "flight_number",        "int"),

    ("OriginAirportID",                  "origin_airport_id",    "int"),
    ("Origin",                           "origin",               "str"),
    ("OriginCityName",                   "origin_city",          "str"),
    ("OriginState",                      "origin_state",         "str"),
    ("OriginStateName",                  "origin_state_name",    "str"),

    ("DestAirportID",                    "dest_airport_id",      "int"),
    ("Dest",                             "dest",                 "str"),
    ("DestCityName",                     "dest_city",            "str"),
    ("DestState",                        "dest_state",           "str"),
    ("DestStateName",                    "dest_state_name",      "str"),

    ("CRSDepTime",                       "crs_dep_time",         "hhmm"),
    ("DepTime",                          "dep_time",             "hhmm"),
    ("DepDelay",                         "dep_delay",            "minutes"),
    ("DepDelayMinutes",                  "dep_delay_minutes",    "minutes"),
    ("DepDel15",                         "dep_del15",            "bool"),
    ("DepTimeBlk",                       "dep_time_block",       "str"),
    ("TaxiOut",                          "taxi_out",             "minutes"),
    ("WheelsOff",                        "wheels_off",           "hhmm"),

    ("WheelsOn",                         "wheels_on",            "hhmm"),
    ("TaxiIn",                           "taxi_in",              "minutes"),
    ("CRSArrTime",                       "crs_arr_time",         "hhmm"),
    ("ArrTime",                          "arr_time",             "hhmm"),
    ("ArrDelay",                         "arr_delay",            "minutes"),
    ("ArrDelayMinutes",                  "arr_delay_minutes",    "minutes"),
    ("ArrDel15",                         "arr_del15",            "bool"),
    ("ArrTimeBlk",                       "arr_time_block",       "str"),

    ("Cancelled",                        "cancelled",            "bool"),
    ("CancellationCode",                 "cancellation_code",    "str"),
    ("Diverted",                         "diverted",             "bool"),

    ("CRSElapsedTime",                   "crs_elapsed_time",     "minutes"),
    ("ActualElapsedTime",                "actual_elapsed_time",  "minutes"),
    ("AirTime",                          "air_time",             "minutes"),
    ("Distance",                         "distance_miles",       "num"),
    ("DistanceGroup",                    "distance_group",       "int"),

    # Cause attribution. BTS populates these only when a flight arrives 15+
    # minutes late; they are NULL, not zero, for on-time flights. The five
    # values sum to ArrDelayMinutes by construction.
    ("CarrierDelay",                     "carrier_delay",        "minutes"),
    ("WeatherDelay",                     "weather_delay",        "minutes"),
    ("NASDelay",                         "nas_delay",            "minutes"),
    ("SecurityDelay",                    "security_delay",       "minutes"),
    ("LateAircraftDelay",                "late_aircraft_delay",  "minutes"),
]

KEEP_COLUMNS = [source for source, _, _ in SCHEMA]

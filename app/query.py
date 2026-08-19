"""Warehouse access for the explorer.

Two things matter here. First, the connection is opened read-only and cached for
the life of the process -- Streamlit re-runs the whole script on every widget
change, and reopening a 10 GB database each time would make the app unusable.
Second, every query runs on its own cursor: one DuckDB connection is shared
across browser sessions, and cursors give each query its own execution context.

Filtered aggregates over the 33.6M-row fact table return in well under a tenth
of a second, so the app queries live rather than pre-aggregating.
"""

from __future__ import annotations

import duckdb
import pandas as pd
import streamlit as st

from pipeline.config import WAREHOUSE


@st.cache_resource(show_spinner=False)
def _db() -> duckdb.DuckDBPyConnection:
    if not WAREHOUSE.exists():
        st.error(
            f"No warehouse at `{WAREHOUSE}`.\n\n"
            "Build it first:\n\n"
            "```\npython -m pipeline.download\n"
            "python -m pipeline.ingest\n"
            "python -m pipeline.build_warehouse\n```"
        )
        st.stop()
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    con.execute("LOAD icu;")
    con.execute("SET TimeZone='UTC'")
    return con


@st.cache_data(show_spinner=False, ttl=3600)
def q(sql: str, params: tuple = ()) -> pd.DataFrame:
    """Run a query and return a DataFrame. Cached on (sql, params)."""
    return _db().cursor().execute(sql, params).df()


class Filters:
    """The filter state, and the SQL predicate it compiles to.

    Kept as one object so every chart in the app is guaranteed to be looking at
    the same slice -- the alternative, each chart building its own WHERE clause,
    is how dashboards end up quietly disagreeing with each other.
    """

    def __init__(self, carriers, airports, date_from, date_to, alias=""):
        self.carriers = list(carriers or [])
        self.airports = list(airports or [])
        self.date_from = date_from
        self.date_to = date_to
        self.alias = f"{alias}." if alias else ""

    def where(self, airport_column: str = "origin") -> tuple[str, tuple]:
        clauses, params = [], []
        a = self.alias
        if self.carriers:
            clauses.append(f"{a}carrier IN ({','.join('?' * len(self.carriers))})")
            params += self.carriers
        if self.airports:
            clauses.append(f"{a}{airport_column} IN ({','.join('?' * len(self.airports))})")
            params += self.airports
        clauses.append(f"{a}flight_date BETWEEN ? AND ?")
        params += [self.date_from, self.date_to]
        return " AND ".join(clauses), tuple(params)

    @property
    def is_narrowed(self) -> bool:
        return bool(self.carriers or self.airports)

    def describe(self) -> str:
        bits = []
        bits.append(", ".join(self.carriers) if self.carriers else "all carriers")
        if self.airports:
            bits.append("via " + ", ".join(self.airports))
        bits.append(f"{self.date_from} to {self.date_to}")
        return " · ".join(bits)

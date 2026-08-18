import duckdb
import pytest

from pipeline.config import WAREHOUSE


@pytest.fixture(scope="session")
def con():
    if not WAREHOUSE.exists():
        pytest.skip(f"{WAREHOUSE} not built -- run python -m pipeline.build_warehouse")
    connection = duckdb.connect(str(WAREHOUSE), read_only=True)
    connection.execute("LOAD icu;")
    # TIMESTAMPTZ stores an instant, but it RENDERS in the session timezone.
    # Pinning to UTC means a query returns the same text on any machine.
    connection.execute("SET TimeZone='UTC'")
    yield connection
    connection.close()


@pytest.fixture(scope="session")
def scalar(con):
    def _scalar(sql: str):
        return con.execute(sql).fetchone()[0]
    return _scalar

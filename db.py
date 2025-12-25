from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from sqlite3 import Connection, connect

import pandas as pd

# Database path - can be overridden for testing
DB_PATH = Path(__file__).resolve().parent / "tournaments.db"


@contextmanager
def get_db_connection(db_path: Path | str | None = None):
    """
    Context manager for database connections.

    Usage:
        with get_db_connection() as conn:
            df = pd.read_sql("SELECT * FROM tournaments", conn)

    Args:
        db_path: Optional path to database file. Defaults to DB_PATH.

    Yields:
        sqlite3.Connection object
    """
    conn = connect(db_path or DB_PATH)
    try:
        yield conn
    finally:
        conn.close()


def db_conn(func):
    """
    Decorator that provides a database connection as the first argument.

    The connection is automatically closed after the function returns.
    """

    @wraps(func)
    def wrapper(*args, **kwargs):
        with get_db_connection() as c:
            return func(c, *args, **kwargs)

    return wrapper


def load_query(filename: str) -> str:
    with open(filename, mode="r", encoding="utf-8") as f:
        return f.read()


def load_data(c: Connection, q_file: str) -> pd.DataFrame:
    return pd.read_sql_query(load_query(q_file), c)


_TRAIL_FILTERS: dict[str, tuple[str, list]] = {
    "Bass Champs": ("AND tournament_trail LIKE ?", ["%Bass Champs%"]),
    "TTZ Team Trail": ("AND tournament_trail = ?", ["TTZ Team Trail"]),
    "TTZ Tuesday Night": ("AND tournament_trail = ?", ["TTZ Tuesday Night"]),
    "TTZ Wednesday Night": ("AND tournament_trail = ?", ["TTZ Wednesday Night"]),
    "TTZ Thursday Night": ("AND tournament_trail = ?", ["TTZ Thursday Night"]),
    "TTZ Championship": ("AND tournament_trail = ?", ["TTZ Championship"]),
    "TTO Team Trail": ("AND tournament_trail = ?", ["TTO Team Trail"]),
    "MediaBass Teams": ("AND tournament_trail = ?", ["MediaBass Teams"]),
    "MediaBass": ("AND tournament_trail = ?", ["MediaBass"]),
}


def get_trail_options() -> list[str]:
    """Return the list of available trail options for filtering."""
    return list(_TRAIL_FILTERS.keys())


def get_trail_filter_sql(trail: str) -> tuple[str, list]:
    """
    Return a SQL WHERE clause fragment and parameters for filtering by trail.

    Args:
        trail: The trail name to filter by (must be a valid trail from get_trail_options())

    Returns:
        Tuple of (where_clause, params) where where_clause is a SQL fragment
        like "AND tournament_trail LIKE ?" and params is a list of values.

    Raises:
        ValueError: If trail is not a recognized trail option.
    """
    if trail not in _TRAIL_FILTERS:
        valid_trails = ", ".join(get_trail_options())
        raise ValueError(f"Invalid trail '{trail}'. Valid options: {valid_trails}")
    return _TRAIL_FILTERS[trail]


def load_data_with_trail(c: Connection, q_file: str, trail: str) -> pd.DataFrame:
    """
    Load data from a query file with optional trail filtering.

    The query file should have a {trail_filter} placeholder where the
    trail filter clause should be inserted.
    """
    query = load_query(q_file)
    where_clause, params = get_trail_filter_sql(trail)
    query = query.replace("{trail_filter}", where_clause)
    return pd.read_sql_query(query, c, params=params if params else None)

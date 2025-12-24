from functools import wraps
from sqlite3 import Connection, connect

import pandas as pd


def db_conn(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        c: Connection = connect(database="tournaments.db")
        try:
            return func(c, *args, **kwargs)
        finally:
            c.close()

    return wrapper


def load_query(filename: str) -> str:
    with open(filename, mode="r", encoding="utf-8") as f:
        return f.read()


def load_data(c: Connection, q_file: str) -> pd.DataFrame:
    return pd.read_sql_query(load_query(q_file), c)


def get_trail_options() -> list[str]:
    """Return the list of available trail options for filtering."""
    return [
        "Bass Champs",
        "TTZ Team Trail",
        "TTZ Tuesday Night",
        "TTZ Wednesday Night",
        "TTZ Thursday Night",
        "TTZ Championship",
    ]


def get_trail_filter_sql(trail: str) -> tuple[str, list]:
    """
    Return a SQL WHERE clause fragment and parameters for filtering by trail.

    Args:
        trail: The trail name to filter by

    Returns:
        Tuple of (where_clause, params) where where_clause is a SQL fragment
        like "AND tournament_trail LIKE ?" and params is a list of values.
    """
    if trail == "Bass Champs":
        return "AND tournament_trail LIKE ?", ["%Bass Champs%"]
    elif trail == "TTZ Team Trail":
        return "AND tournament_trail = ?", ["TTZ Team Trail"]
    elif trail == "TTZ Tuesday Night":
        return "AND tournament_trail = ?", ["TTZ Tuesday Night"]
    elif trail == "TTZ Wednesday Night":
        return "AND tournament_trail = ?", ["TTZ Wednesday Night"]
    elif trail == "TTZ Thursday Night":
        return "AND tournament_trail = ?", ["TTZ Thursday Night"]
    elif trail == "TTZ Championship":
        return "AND tournament_trail = ?", ["TTZ Championship"]
    else:
        return "", []


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

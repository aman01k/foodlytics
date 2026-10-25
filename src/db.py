"""Small DB helpers shared by analysis modules, tests and the dashboard."""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, text

from config.settings import db_url


@lru_cache(maxsize=1)
def engine():
    return create_engine(db_url())


def query(sql: str, **params) -> pd.DataFrame:
    with engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params or None)


def named_queries(path: Path) -> dict[str, str]:
    """Parse a .sql file into {name: sql} using `-- name: xxx` markers."""
    parts = re.split(r"^--\s*name:\s*(\S+)\s*$", path.read_text(), flags=re.M)
    return {parts[i]: parts[i + 1].strip() for i in range(1, len(parts), 2)}

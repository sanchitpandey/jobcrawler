from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .settings import get_settings


def get_db_path() -> str:
    return get_settings().paths.db_path


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(get_db_path())
    try:
        yield conn
    finally:
        conn.close()


def fetch_all(query: str, params: tuple = ()) -> list[sqlite3.Row]:
    with db_connection() as conn:
        conn.row_factory = sqlite3.Row
        return conn.execute(query, params).fetchall()


def execute(query: str, params: tuple = ()) -> None:
    with db_connection() as conn:
        conn.execute(query, params)
        conn.commit()

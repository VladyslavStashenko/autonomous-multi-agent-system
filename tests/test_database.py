from __future__ import annotations

import sqlite3

from storage.database import init_db


def test_init_db_creates_expected_tables(isolated_database) -> None:
    init_db()

    connection = sqlite3.connect(isolated_database)
    try:
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
    finally:
        connection.close()

    assert {"agent_runs", "agent_steps", "memory_entries"}.issubset(table_names)

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

import cli.commands as commands
from config import Settings
from storage.database import init_db
from storage.repository import save_memory_entry
from ui.theme import THEMES


def test_clear_command_removes_json_state_session_and_sqlite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_database: Path,
) -> None:
    memory_file = tmp_path / ".agent_memory" / "memory.json"
    state_file = tmp_path / ".agent_state" / "last_run.json"
    session_file = tmp_path / "session.json"

    init_db()
    save_memory_entry(
        {
            "task": "remember",
            "status": "done",
            "created_files": [],
            "ran_commands": [],
            "read_files": [],
            "timestamp": "2025-01-01T00:00:00",
        }
    )
    memory_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.parent.mkdir(parents=True, exist_ok=True)
    memory_file.write_text("{}", encoding="utf-8")
    state_file.write_text("{}", encoding="utf-8")
    session_file.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(commands, "SESSION_FILE", session_file)
    cli_dir = tmp_path / "cli"
    cli_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(commands, "__file__", str(cli_dir / "commands.py"))
    monkeypatch.setattr(builtins, "input", lambda _: "y")

    handled, *_ = commands.handle_command(
        "/clear",
        THEMES["cyan"],
        "technical",
        "single",
        Settings(api_key="x", api_keys=["x"]),
        {},
    )

    assert handled is True
    assert memory_file.exists() is False
    assert state_file.exists() is False
    assert session_file.exists() is False
    assert isolated_database.exists() is False

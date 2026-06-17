from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import memory
from agents.state import AgentState
from storage.database import init_db


def test_load_memory_returns_empty_dict_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_database: Path,
) -> None:
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "memory.json")
    init_db()

    assert memory.load_memory() == {}


def test_save_memory_creates_entries_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_database: Path,
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    init_db()

    state = AgentState(task="save memory")
    state.add_step(
        step_number=1,
        decision={"action": "read_file", "args": {"path": "notes.txt"}},
        result={"ok": True},
    )
    state.finish("done", "saved")

    memory.save_memory(state)

    payload = json.loads(memory_file.read_text(encoding="utf-8"))
    assert "entries" in payload
    assert len(payload["entries"]) == 1
    assert payload["entries"][0]["task"] == "save memory"
    assert payload["entries"][0]["read_files"] == ["notes.txt"]


def test_save_memory_keeps_only_last_ten_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_database: Path,
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    init_db()

    for index in range(12):
        state = AgentState(task=f"task-{index}")
        state.finish("done", "ok")
        memory.save_memory(state)

    payload = memory.load_memory()
    entries = payload["entries"]
    assert len(entries) == 10
    assert entries[0]["task"] == "task-2"
    assert entries[-1]["task"] == "task-11"


def test_load_memory_reads_saved_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_database: Path,
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    init_db()
    memory_file.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "task": "loaded",
                        "status": "done",
                        "timestamp": "2025-01-01T00:00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = memory.load_memory()

    assert payload == {
        "entries": [
            {
                "task": "loaded",
                "status": "done",
                "created_files": [],
                "ran_commands": [],
                "read_files": [],
                "timestamp": "2025-01-01T00:00:00",
            }
        ]
    }


def test_load_memory_skips_invalid_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    isolated_database: Path,
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    memory_file.write_text(
        json.dumps(
            {
                "entries": [
                    {"task": "loaded", "status": "done", "timestamp": "2025-01-01T00:00:00"},
                    {"task": "broken"},
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = memory.load_memory()

    assert payload == {
        "entries": [
            {
                "task": "loaded",
                "status": "done",
                "created_files": [],
                "ran_commands": [],
                "read_files": [],
                "timestamp": "2025-01-01T00:00:00",
            }
        ]
    }


def test_load_memory_falls_back_to_json_when_database_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    monkeypatch.setattr(memory, "get_recent_memory_entries", lambda limit=10: (_ for _ in ()).throw(RuntimeError("db down")))
    memory_file.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "task": "json fallback",
                        "status": "done",
                        "timestamp": "2025-01-01T00:00:00",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    payload = memory.load_memory()

    assert payload["entries"][0]["task"] == "json fallback"

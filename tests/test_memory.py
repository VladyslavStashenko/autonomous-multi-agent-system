from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents import memory
from agents.state import AgentState


def test_load_memory_returns_empty_dict_when_file_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(memory, "MEMORY_FILE", tmp_path / "memory.json")

    assert memory.load_memory() == {}


def test_save_memory_creates_entries_structure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)

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
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)

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
) -> None:
    memory_file = tmp_path / "memory.json"
    monkeypatch.setattr(memory, "MEMORY_FILE", memory_file)
    memory_file.write_text(
        json.dumps({"entries": [{"task": "loaded", "status": "done"}]}),
        encoding="utf-8",
    )

    payload = memory.load_memory()

    assert payload == {"entries": [{"task": "loaded", "status": "done"}]}

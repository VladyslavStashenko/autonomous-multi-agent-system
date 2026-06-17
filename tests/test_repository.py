from __future__ import annotations

from storage.database import init_db
from storage.repository import get_last_run, get_recent_memory_entries, save_memory_entry, save_run, save_run_steps


def test_save_memory_entry_persists_record(isolated_database) -> None:
    init_db()

    save_memory_entry(
        {
            "task": "remember this",
            "status": "done",
            "created_files": ["notes.txt"],
            "ran_commands": ["python app.py"],
            "read_files": ["app.py"],
            "timestamp": "2025-01-01T00:00:00",
        }
    )

    entries = get_recent_memory_entries()

    assert len(entries) == 1
    assert entries[0]["task"] == "remember this"
    assert entries[0]["created_files"] == ["notes.txt"]


def test_get_recent_memory_entries_returns_latest_entries(isolated_database) -> None:
    init_db()

    for index in range(12):
        save_memory_entry(
            {
                "task": f"task-{index}",
                "status": "done",
                "created_files": [],
                "ran_commands": [],
                "read_files": [],
                "timestamp": f"2025-01-01T00:00:{index:02d}",
            }
        )

    entries = get_recent_memory_entries(limit=10)

    assert len(entries) == 10
    assert entries[0]["task"] == "task-2"
    assert entries[-1]["task"] == "task-11"


def test_save_run_and_steps_are_returned_by_get_last_run(isolated_database) -> None:
    init_db()

    run_id = save_run(
        run_id="run-1",
        task="ship feature",
        agent_type="single",
        status="done",
        summary="completed",
        created_at="2025-01-01T00:00:00",
    )
    save_run_steps(
        run_id,
        [
            {
                "step": 1,
                "decision": {
                    "action": "read_file",
                    "reason": "inspect file",
                    "args": {"path": "main.py"},
                },
                "result": {"ok": True, "content": "print('hi')"},
            }
        ],
    )

    last_run = get_last_run()

    assert last_run is not None
    assert last_run["id"] == "run-1"
    assert last_run["task"] == "ship feature"
    assert last_run["status"] == "done"
    assert last_run["steps_history"][0]["decision"]["action"] == "read_file"

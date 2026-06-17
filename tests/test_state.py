from __future__ import annotations

import json
from pathlib import Path

from agents.state import AgentState
from storage.repository import get_last_run


def test_add_step_populates_all_tracking_lists() -> None:
    state = AgentState(task="task")
    decision = {"action": "read_file"}
    result = {"ok": True}

    state.add_step(step_number=1, decision=decision, result=result)

    assert state.decisions == [decision]
    assert state.tool_results == [result]
    assert state.steps_history == [{"step": 1, "decision": decision, "result": result}]


def test_finish_sets_status_and_summary() -> None:
    state = AgentState(task="task")

    state.finish("done", "completed")

    assert state.final_status == "done"
    assert state.final_summary == "completed"


def test_to_dict_returns_expected_dataclass_structure() -> None:
    state = AgentState(task="task")
    state.add_step(step_number=1, decision={"action": "read_file"}, result={"ok": True})
    state.finish("done", "completed")

    payload = state.to_dict()

    assert payload["task"] == "task"
    assert payload["final_status"] == "done"
    assert payload["final_summary"] == "completed"
    assert payload["steps_history"][0]["step"] == 1


def test_save_writes_json_file_and_persists_run(tmp_path: Path, isolated_database: Path) -> None:
    target = tmp_path / "state" / "run.json"
    state = AgentState(task="task")
    state.add_step(step_number=1, decision={"action": "read_file"}, result={"ok": True})
    state.finish("done", "completed")

    state.save(target)

    assert target.exists()
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["task"] == "task"
    assert payload["final_status"] == "done"
    assert payload["steps_history"][0]["decision"]["action"] == "read_file"

    last_run = get_last_run()
    assert last_run is not None
    assert last_run["task"] == "task"
    assert last_run["status"] == "done"

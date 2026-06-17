from __future__ import annotations

from pathlib import Path

import pytest

from agents.state import AgentState
from tools import filesystem, security


@pytest.fixture
def isolated_project_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(security, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr(filesystem, "PROJECT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def sample_state() -> AgentState:
    state = AgentState(task="test task")
    state.add_step(
        step_number=1,
        decision={
            "action": "read_file",
            "args": {"path": "example.txt"},
        },
        result={"ok": True, "content": "hello"},
    )
    state.finish("done", "completed")
    return state

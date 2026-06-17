from __future__ import annotations

from unittest.mock import MagicMock

import pytest

import agents.orchestrator as orchestrator_module
from agents.orchestrator import OrchestratorAgent


@pytest.fixture(autouse=True)
def disable_orchestrator_persistence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orchestrator_module, "save_memory", lambda state: None)


@pytest.fixture
def base_orchestrator(monkeypatch: pytest.MonkeyPatch) -> OrchestratorAgent:
    monkeypatch.setattr(orchestrator_module.AgentState, "save", lambda self, path=None: None)
    return OrchestratorAgent(
        pool=MagicMock(),
        model="test-model",
        worker=MagicMock(),
        evaluator=MagicMock(),
        max_steps=3,
    )


def test_plan_subtasks_parses_valid_json_array(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        base_orchestrator,
        "_call_api",
        lambda **kwargs: type("Response", (), {"text": '["Read file", "Count lines"]'})(),
    )

    result = base_orchestrator._plan_subtasks("Count lines")

    assert result == ["Read file", "Count lines"]


def test_orchestrator_run_fails_on_malformed_planner_response(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        base_orchestrator,
        "_call_api",
        lambda **kwargs: type("Response", (), {"text": "not-json"})(),
    )

    result = base_orchestrator.run("Count lines")

    assert result["status"] == "fail"
    assert "Planner failed" in result["summary"]


def test_orchestrator_successful_pipeline(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_orchestrator, "_plan_subtasks", lambda task: ["Step 1", "Step 2"])
    monkeypatch.setattr(
        orchestrator_module._CoderAgent,
        "run",
        lambda self, subtask: {"status": "done", "summary": f"done {subtask}", "state": {"steps_history": []}},
    )
    monkeypatch.setattr(
        base_orchestrator,
        "_review_results",
        lambda task, plan, results: {"status": "SUCCESS", "summary": "all good", "issues": []},
    )

    result = base_orchestrator.run("Count lines")

    assert result["status"] == "done"
    assert result["summary"] == "all good"
    assert len(result["subtasks"]) == 2


def test_orchestrator_failed_subtask_stops_pipeline(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_orchestrator, "_plan_subtasks", lambda task: ["Step 1", "Step 2"])
    base_orchestrator.max_subtask_retries = 0
    coder_runs: list[str] = []

    def fake_coder_run(self, subtask: str):
        coder_runs.append(subtask)
        if subtask == "Step 1":
            return {"status": "fail", "summary": "broken", "state": {"steps_history": []}}
        return {"status": "done", "summary": "done", "state": {"steps_history": []}}

    monkeypatch.setattr(orchestrator_module._CoderAgent, "run", fake_coder_run)

    result = base_orchestrator.run("Count lines")

    assert result["status"] == "fail"
    assert coder_runs == ["Step 1"]
    assert "Subtask failed: Step 1" in result["summary"]


def test_orchestrator_reviewer_fail_triggers_repair_cycle(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_orchestrator, "_plan_subtasks", lambda task: ["Step 1"])
    coder_runs: list[str] = []

    def fake_coder_run(self, subtask: str):
        coder_runs.append(subtask)
        return {"status": "done", "summary": f"done {subtask}", "state": {"steps_history": []}}

    review_results = iter(
        [
            {"status": "FAIL", "summary": "need repair", "issues": [{"problem": "x"}]},
            {"status": "SUCCESS", "summary": "fixed", "issues": []},
        ]
    )

    monkeypatch.setattr(orchestrator_module._CoderAgent, "run", fake_coder_run)
    monkeypatch.setattr(base_orchestrator, "_review_results", lambda task, plan, results: next(review_results))

    result = base_orchestrator.run("Count lines")

    assert result["status"] == "done"
    assert result["summary"] == "fixed"
    assert len(coder_runs) == 2
    assert "Fix" in coder_runs[1] or "Виправ" in coder_runs[1]


def test_orchestrator_reviewer_exception_returns_fail(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(base_orchestrator, "_plan_subtasks", lambda task: ["Step 1"])
    monkeypatch.setattr(
        orchestrator_module._CoderAgent,
        "run",
        lambda self, subtask: {"status": "done", "summary": "done", "state": {"steps_history": []}},
    )

    def boom(task, plan, results):
        raise RuntimeError("review exploded")

    monkeypatch.setattr(base_orchestrator, "_review_results", boom)

    result = base_orchestrator.run("Count lines")

    assert result["status"] == "fail"
    assert "Reviewer failed: review exploded" == result["summary"]


def test_review_results_normalizes_redundant_summary(
    base_orchestrator: OrchestratorAgent,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        base_orchestrator,
        "_call_api",
        lambda **kwargs: type(
            "Response",
            (),
            {
                "text": '{"status":"SUCCESS","summary":"Done: Updated files.\\n\\n**Short summary:**\\nUpdated files.","issues":[]}'
            },
        )(),
    )

    result = base_orchestrator._review_results("Update files", ["Step 1"], [{"summary": "ok"}])

    assert result["status"] == "SUCCESS"
    assert result["summary"] == "Updated files."

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import agents.autonomous_agent as autonomous_module
from agents.autonomous_agent import AutonomousAgent


def make_function_call_response(name: str, args: dict | None = None) -> SimpleNamespace:
    function_call = SimpleNamespace(name=name, args=args or {})
    part = SimpleNamespace(function_call=function_call, text=None)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(text="", candidates=[candidate])


def make_text_response(text: str) -> SimpleNamespace:
    part = SimpleNamespace(text=text)
    content = SimpleNamespace(parts=[part])
    candidate = SimpleNamespace(content=content)
    return SimpleNamespace(text=text, candidates=[candidate])


class SequenceAutonomousAgent(AutonomousAgent):
    def __init__(self, responses, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._responses = list(responses)
        self.api_call_count = 0

    def _call_api(self, **kwargs):
        self.api_call_count += 1
        response = self._responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


@pytest.fixture
def fake_worker():
    return MagicMock()


@pytest.fixture
def fake_evaluator():
    evaluator = MagicMock()
    evaluator.evaluate_state.return_value = {
        "status": "SUCCESS",
        "summary": "ok",
        "retry_step_indexes": [],
    }
    return evaluator


@pytest.fixture(autouse=True)
def disable_memory_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(autonomous_module, "load_memory", lambda: {})
    monkeypatch.setattr(autonomous_module, "save_memory", lambda state: None)
    monkeypatch.setattr(autonomous_module.AgentState, "save", lambda self, path=None: None)


def test_autonomous_agent_happy_path(fake_worker, fake_evaluator) -> None:
    fake_worker.execute_step.return_value = {"ok": True, "content": "hello"}
    agent = SequenceAutonomousAgent(
        responses=[
            make_function_call_response("read_file", {"path": "demo.txt"}),
            make_text_response("Completed successfully."),
        ],
        pool=MagicMock(),
        model="test-model",
        worker=fake_worker,
        evaluator=fake_evaluator,
        max_steps=3,
    )

    result = agent.run("Read file")

    assert result["status"] == "done"
    assert result["summary"] == "Completed successfully."
    fake_worker.execute_step.assert_called_once_with({"action": "read_file", "path": "demo.txt"})


def test_autonomous_agent_plain_text_before_tool_call_continues(fake_worker, fake_evaluator) -> None:
    fake_worker.execute_step.return_value = {"ok": True, "content": "hello"}
    agent = SequenceAutonomousAgent(
        responses=[
            make_text_response("Just text before tools"),
            make_function_call_response("read_file", {"path": "demo.txt"}),
            make_text_response("Done after tool."),
        ],
        pool=MagicMock(),
        model="test-model",
        worker=fake_worker,
        evaluator=fake_evaluator,
        max_steps=5,
    )

    result = agent.run("Read file")

    assert result["status"] == "done"
    assert result["summary"] == "Done after tool."
    assert agent.api_call_count == 3
    fake_worker.execute_step.assert_called_once()


def test_autonomous_agent_api_failure_returns_fail(fake_worker, fake_evaluator) -> None:
    agent = SequenceAutonomousAgent(
        responses=[RuntimeError("boom")],
        pool=MagicMock(),
        model="test-model",
        worker=fake_worker,
        evaluator=fake_evaluator,
        max_steps=2,
    )

    result = agent.run("Read file")

    assert result["status"] == "fail"
    assert "Failed to get model response" in result["summary"]


def test_autonomous_agent_returns_max_steps_when_never_finishes(fake_worker, fake_evaluator) -> None:
    fake_worker.execute_step.return_value = {"ok": True, "content": "hello"}
    agent = SequenceAutonomousAgent(
        responses=[
            make_function_call_response("read_file", {"path": "demo.txt"}),
            make_function_call_response("read_file", {"path": "demo.txt"}),
            make_function_call_response("read_file", {"path": "demo.txt"}),
        ],
        pool=MagicMock(),
        model="test-model",
        worker=fake_worker,
        evaluator=fake_evaluator,
        max_steps=3,
    )

    result = agent.run("Read file")

    assert result["status"] == "max_steps"
    assert "max_steps=3" in result["summary"]
    assert fake_worker.execute_step.call_count == 3


def test_autonomous_agent_evaluator_feedback_attaches_only_for_failed_tool(
    fake_worker,
) -> None:
    responses = [
        make_function_call_response("read_file", {"path": "demo.txt"}),
        make_text_response("Done."),
    ]

    failing_evaluator = MagicMock()
    failing_evaluator.evaluate_state.return_value = {
        "status": "FAIL",
        "summary": "bad step",
        "retry_step_indexes": [0],
    }

    fake_worker.execute_step.return_value = {"ok": False, "error": "cannot read"}
    failing_agent = SequenceAutonomousAgent(
        responses=list(responses),
        pool=MagicMock(),
        model="test-model",
        worker=fake_worker,
        evaluator=failing_evaluator,
        max_steps=3,
    )
    failed_result = failing_agent.run("Read file")
    failed_step = failed_result["state"]["steps_history"][0]["result"]

    assert "evaluator" in failed_step
    assert failing_evaluator.evaluate_state.called is True

    ok_worker = MagicMock()
    ok_worker.execute_step.return_value = {"ok": True, "content": "hello"}
    ok_evaluator = MagicMock()
    ok_evaluator.evaluate_state.return_value = {
        "status": "FAIL",
        "summary": "should not attach",
        "retry_step_indexes": [0],
    }
    ok_agent = SequenceAutonomousAgent(
        responses=[
            make_function_call_response("read_file", {"path": "demo.txt"}),
            make_text_response("Done."),
        ],
        pool=MagicMock(),
        model="test-model",
        worker=ok_worker,
        evaluator=ok_evaluator,
        max_steps=3,
    )
    ok_result = ok_agent.run("Read file")
    ok_step = ok_result["state"]["steps_history"][0]["result"]

    assert "evaluator" not in ok_step
    assert ok_evaluator.evaluate_state.called is True

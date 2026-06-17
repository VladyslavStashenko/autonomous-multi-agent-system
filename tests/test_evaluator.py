from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from agents.evaluator import Evaluator


def make_evaluator_with_response(text: str) -> Evaluator:
    response = SimpleNamespace(text=text)
    client = MagicMock()
    client.models.generate_content.return_value = response
    return Evaluator(client_getter=lambda: client)


def test_evaluate_parses_valid_json_response() -> None:
    evaluator = make_evaluator_with_response(
        '{"status":"SUCCESS","summary":"done","retry_step_indexes":[]}'
    )

    result = evaluator.evaluate("task", [{"step": 1}], [{"ok": True}])

    assert result == {
        "status": "SUCCESS",
        "summary": "done",
        "retry_step_indexes": [],
    }


def test_evaluate_parses_json_wrapped_in_markdown_fence() -> None:
    evaluator = make_evaluator_with_response(
        '```json\n{"status":"FAIL","summary":"retry","retry_step_indexes":[0]}\n```'
    )

    result = evaluator.evaluate("task", [{"step": 1}], [{"ok": False}])

    assert result == {
        "status": "FAIL",
        "summary": "retry",
        "retry_step_indexes": [0],
    }


def test_evaluate_falls_back_for_invalid_json() -> None:
    evaluator = make_evaluator_with_response("not a json payload")

    result = evaluator.evaluate(
        "task",
        [{"step": 1}, {"step": 2}],
        [{"ok": True}, {"ok": False}],
    )

    assert result == {
        "status": "FAIL",
        "summary": "Could not parse evaluator output; retrying failed steps.",
        "retry_step_indexes": [1],
    }


def test_evaluate_falls_back_for_invalid_status() -> None:
    evaluator = make_evaluator_with_response(
        '{"status":"MAYBE","summary":"unknown","retry_step_indexes":[]}'
    )

    result = evaluator.evaluate("task", [{"step": 1}], [{"ok": True}])

    assert result == {
        "status": "SUCCESS",
        "summary": "Completed based on tool results.",
        "retry_step_indexes": [],
    }

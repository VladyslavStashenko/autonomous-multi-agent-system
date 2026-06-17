from __future__ import annotations

from cli.router import resolve_agent_type, route_agent_type


def test_route_agent_type_prefers_single_for_short_local_task() -> None:
    result = route_agent_type("Порахуй рядки у файлі test_calculator.py")

    assert result["agent_type"] == "single"
    assert result["score"] < result["threshold"]


def test_route_agent_type_prefers_multi_for_large_multifile_task() -> None:
    task = """
    Створи проєкт task_tracker.
    Вимоги:
    - створи task_tracker/main.py
    - створи task_tracker/storage.py
    - створи README.md
    - додай tests/test_storage.py
    - додай тести і документацію
    """

    result = route_agent_type(task)

    assert result["agent_type"] == "multi"
    assert result["score"] >= result["threshold"]
    assert result["reasons"]


def test_resolve_agent_type_bypasses_routing_for_explicit_single() -> None:
    result = resolve_agent_type("single", "Створи проєкт з кількох файлів")

    assert result["effective_agent_type"] == "single"
    assert result["routing_applied"] is False


def test_resolve_agent_type_bypasses_routing_for_explicit_multi() -> None:
    result = resolve_agent_type("multi", "Порахуй рядки у файлі test.py")

    assert result["effective_agent_type"] == "multi"
    assert result["routing_applied"] is False


def test_resolve_agent_type_routes_auto_without_changing_selected_mode() -> None:
    result = resolve_agent_type("auto", "Порахуй рядки у файлі test.py")

    assert result["selected_agent_type"] == "auto"
    assert result["effective_agent_type"] == "single"
    assert result["routing_applied"] is True

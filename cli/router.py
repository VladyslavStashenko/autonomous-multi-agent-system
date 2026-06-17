from __future__ import annotations

import re
from typing import Any


MULTI_KEYWORDS = {
    "tests": "tests mentioned",
    "pytest": "tests mentioned",
    "readme": "documentation mentioned",
    "project": "project creation requested",
    "sqlite": "infrastructure/storage change mentioned",
    "fastapi": "infrastructure change mentioned",
    "refactor": "refactor requested",
    "architecture": "architecture change requested",
    "архітектура": "architecture change requested",
    "рефактор": "refactor requested",
    "додай тести": "tests mentioned",
    "створи проєкт": "project creation requested",
    "онови модулі": "multiple modules mentioned",
    "перероби": "broad rewrite requested",
    "кілька файлів": "multiple files mentioned",
}

SINGLE_HINT_KEYWORDS = (
    "прочитай файл",
    "порахуй рядки",
    "виправ помилку",
    "запусти тести",
    "поясни код",
    "подивись файл",
    "read file",
    "count lines",
    "explain code",
    "run tests",
)


def route_agent_type(task: str) -> dict[str, Any]:
    normalized = task.lower().strip()
    reasons: list[str] = []
    score = 0

    line_count = len([line for line in task.splitlines() if line.strip()])
    if len(task) >= 450:
        score += 2
        reasons.append("long task description")
    if line_count >= 6:
        score += 2
        reasons.append("multi-step task")
    if task.count("- ") >= 3 or task.count("1.") >= 1:
        score += 2
        reasons.append("requirements list detected")

    file_mentions = set(re.findall(r"[\w./\\-]+\.(?:py|md|txt|json|docx|yaml|yml|toml|ini)", normalized))
    if len(file_mentions) >= 2:
        score += 3
        reasons.append("multiple files mentioned")
    elif len(file_mentions) == 1:
        score -= 1
        reasons.append("single file focus")

    matched_multi_reasons: set[str] = set()
    for keyword, reason in MULTI_KEYWORDS.items():
        if keyword in normalized and reason not in matched_multi_reasons:
            score += 2
            reasons.append(reason)
            matched_multi_reasons.add(reason)

    if any(keyword in normalized for keyword in SINGLE_HINT_KEYWORDS):
        score -= 2
        reasons.append("simple local action")

    if len(task) <= 120 and line_count <= 2:
        score -= 1
        reasons.append("short prompt")

    threshold = 4
    agent_type = "multi" if score >= threshold else "single"
    return {
        "agent_type": agent_type,
        "score": score,
        "threshold": threshold,
        "reasons": reasons[:4],
    }


def resolve_agent_type(selected_agent_type: str, task: str) -> dict[str, Any]:
    normalized_selected = selected_agent_type.lower().strip()
    if normalized_selected in {"single", "multi"}:
        return {
            "selected_agent_type": normalized_selected,
            "effective_agent_type": normalized_selected,
            "routing_applied": False,
            "score": None,
            "threshold": None,
            "reasons": [],
        }

    routed = route_agent_type(task)
    return {
        "selected_agent_type": "auto",
        "effective_agent_type": routed["agent_type"],
        "routing_applied": True,
        "score": routed["score"],
        "threshold": routed["threshold"],
        "reasons": routed["reasons"],
    }

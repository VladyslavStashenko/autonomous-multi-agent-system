from __future__ import annotations

from datetime import datetime
from dataclasses import replace
from pathlib import Path
from typing import Any

from config import Settings
from ui.theme import Theme

SESSION_FILE = Path(__file__).resolve().parent / ".agent_state" / "session.json"


def load_session() -> dict[str, Any]:
    if not SESSION_FILE.exists():
        return {}
    try:
        import json

        data = json.loads(SESSION_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_session(session: dict[str, Any]) -> None:
    try:
        import json

        payload = {
            **session,
            "last_used_at": datetime.now().isoformat(timespec="seconds"),
        }
        SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
        SESSION_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def get_effective_settings(base_settings: Settings, config_overrides: dict[str, Any]) -> Settings:
    return replace(
        base_settings,
        model=str(config_overrides.get("model", base_settings.model)),
        max_agent_steps=int(config_overrides.get("max_agent_steps", base_settings.max_agent_steps)),
    )


def build_session_state(
    base_settings: Settings,
    config_overrides: dict[str, Any],
    theme: Theme,
    mode: str,
    agent_type: str,
) -> dict[str, Any]:
    settings = get_effective_settings(base_settings, config_overrides)
    return {
        "model": settings.model,
        "max_agent_steps": settings.max_agent_steps,
        "theme": theme.name,
        "mode": mode,
        "agent_type": agent_type,
    }

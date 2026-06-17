from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.state import AgentState
from schemas.models import MemoryEntry
from storage.repository import get_recent_memory_entries, save_memory_entry


MEMORY_FILE = Path(__file__).resolve().parent.parent / ".agent_memory" / "memory.json"


def _load_memory_from_json_fallback() -> dict[str, Any]:
    if not MEMORY_FILE.exists():
        return {}

    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        validated_entries = []
        for entry in data["entries"]:
            try:
                validated_entries.append(MemoryEntry.model_validate(entry).model_dump())
            except Exception:
                continue
        return {"entries": validated_entries} if validated_entries else {}
    if isinstance(data, list):
        validated_entries = []
        for entry in data:
            try:
                validated_entries.append(MemoryEntry.model_validate(entry).model_dump())
            except Exception:
                continue
        return {"entries": validated_entries} if validated_entries else {}
    return {}


def load_memory() -> dict[str, Any]:
    try:
        entries = get_recent_memory_entries(limit=10)
    except Exception:
        return _load_memory_from_json_fallback()
    return {"entries": entries} if entries else _load_memory_from_json_fallback()


def save_memory(state: AgentState) -> None:
    created_files: list[str] = []
    ran_commands: list[str] = []
    read_files: list[str] = []

    for step in state.steps_history:
        decision = step.get("decision", {})
        action = decision.get("action", "")
        args = decision.get("args", {})

        if action in {"write_file", "apply_patch"}:
            path = str(args.get("path", "")).strip()
            if path:
                created_files.append(path)
        elif action == "run_command":
            command = str(args.get("command", "")).strip()
            if command:
                ran_commands.append(command)
        elif action == "read_file":
            path = str(args.get("path", "")).strip()
            if path:
                read_files.append(path)

    entry = MemoryEntry(
        task=state.task,
        status=state.final_status,
        created_files=created_files,
        ran_commands=ran_commands,
        read_files=read_files,
        timestamp=datetime.now().isoformat(timespec="seconds"),
    )
    save_memory_entry(entry)
    entries = get_recent_memory_entries(limit=10)

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

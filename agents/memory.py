from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agents.state import AgentState


MEMORY_FILE = Path(__file__).resolve().parent.parent / ".agent_memory" / "memory.json"


def load_memory() -> dict[str, Any]:
    if not MEMORY_FILE.exists():
        return {}

    try:
        data = json.loads(MEMORY_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}

    if isinstance(data, dict) and isinstance(data.get("entries"), list):
        return {"entries": data["entries"]}
    if isinstance(data, list):
        return {"entries": data}
    return {}


def save_memory(state: AgentState) -> None:
    memory = load_memory()
    entries = list(memory.get("entries", []))

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

    entries.append(
        {
            "task": state.task,
            "status": state.final_status,
            "created_files": created_files,
            "ran_commands": ran_commands,
            "read_files": read_files,
            "timestamp": datetime.now().isoformat(timespec="seconds"),
        }
    )
    entries = entries[-10:]

    MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_FILE.write_text(
        json.dumps({"entries": entries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


STATE_DIR = Path(__file__).resolve().parent.parent / ".agent_state"
STATE_FILE = STATE_DIR / "last_run.json"


@dataclass
class AgentState:
    task: str
    steps_history: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    final_status: str = "running"
    final_summary: str = ""

    def add_step(self, step_number: int, decision: dict[str, Any], result: dict[str, Any]) -> None:
        self.decisions.append(decision)
        self.tool_results.append(result)
        self.steps_history.append(
            {
                "step": step_number,
                "decision": decision,
                "result": result,
            }
        )

    def finish(self, status: str, summary: str) -> None:
        self.final_status = status
        self.final_summary = summary

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def save(self, path: Path = STATE_FILE) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

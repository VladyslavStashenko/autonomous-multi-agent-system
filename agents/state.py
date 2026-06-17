from __future__ import annotations

import json
from datetime import datetime
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4


STATE_DIR = Path(__file__).resolve().parent.parent / ".agent_state"
STATE_FILE = STATE_DIR / "last_run.json"


@dataclass
class AgentState:
    task: str
    agent_type: str = "single"
    run_id: str = field(default_factory=lambda: uuid4().hex)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
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
        from storage.repository import save_run, save_run_steps

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        save_run(
            run_id=self.run_id,
            task=self.task,
            agent_type=self.agent_type,
            status=self.final_status,
            summary=self.final_summary,
            created_at=self.created_at,
        )
        save_run_steps(self.run_id, self.steps_history)

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from sqlalchemy import delete, desc, select

from schemas.models import MemoryEntry
from storage.database import get_session, init_db
from storage.models import AgentRun, AgentStep, MemoryEntryRecord


def save_run(
    *,
    run_id: str,
    task: str,
    status: str,
    summary: str,
    created_at: str,
    agent_type: str | None = None,
) -> str:
    init_db()
    with get_session() as session:
        run = session.get(AgentRun, run_id)
        created_at_value = datetime.fromisoformat(created_at)
        if run is None:
            run = AgentRun(
                id=run_id,
                task=task,
                agent_type=agent_type,
                status=status,
                summary=summary,
                created_at=created_at_value,
            )
            session.add(run)
        else:
            run.task = task
            run.agent_type = agent_type
            run.status = status
            run.summary = summary
            run.created_at = created_at_value
        session.commit()
    return run_id


def save_run_steps(run_id: str, steps_history: list[dict[str, Any]]) -> None:
    init_db()
    with get_session() as session:
        session.execute(delete(AgentStep).where(AgentStep.run_id == run_id))
        for step in steps_history:
            decision = dict(step.get("decision", {}))
            result = dict(step.get("result", {}))
            args = decision.get("args", {})
            session.add(
                AgentStep(
                    run_id=run_id,
                    step_number=int(step.get("step", 0)),
                    action=str(decision.get("action", "")),
                    reason=str(decision.get("reason", "")),
                    args_json=json.dumps(args, ensure_ascii=False),
                    result_json=json.dumps(result, ensure_ascii=False),
                )
            )
        session.commit()


def save_memory_entry(entry: MemoryEntry | dict[str, Any]) -> None:
    init_db()
    payload = entry.model_dump() if isinstance(entry, MemoryEntry) else MemoryEntry.model_validate(entry).model_dump()
    with get_session() as session:
        session.add(
            MemoryEntryRecord(
                task=payload["task"],
                status=payload["status"],
                created_files_json=json.dumps(payload["created_files"], ensure_ascii=False),
                ran_commands_json=json.dumps(payload["ran_commands"], ensure_ascii=False),
                read_files_json=json.dumps(payload["read_files"], ensure_ascii=False),
                timestamp=payload["timestamp"],
            )
        )
        session.commit()


def get_recent_memory_entries(limit: int = 10) -> list[dict[str, Any]]:
    init_db()
    with get_session() as session:
        rows = session.execute(
            select(MemoryEntryRecord).order_by(desc(MemoryEntryRecord.id)).limit(limit)
        ).scalars().all()
    rows = list(reversed(rows))
    return [
        MemoryEntry(
            task=row.task,
            status=row.status,
            created_files=json.loads(row.created_files_json),
            ran_commands=json.loads(row.ran_commands_json),
            read_files=json.loads(row.read_files_json),
            timestamp=row.timestamp,
        ).model_dump()
        for row in rows
    ]


def get_last_run() -> dict[str, Any] | None:
    init_db()
    with get_session() as session:
        run = session.execute(select(AgentRun).order_by(desc(AgentRun.created_at))).scalar_one_or_none()
        if run is None:
            return None
        steps = session.execute(
            select(AgentStep).where(AgentStep.run_id == run.id).order_by(AgentStep.step_number)
        ).scalars().all()
    return {
        "id": run.id,
        "task": run.task,
        "agent_type": run.agent_type,
        "status": run.status,
        "summary": run.summary,
        "created_at": run.created_at.isoformat(timespec="seconds"),
        "steps_history": [
            {
                "step": step.step_number,
                "decision": {
                    "action": step.action,
                    "reason": step.reason,
                    "args": json.loads(step.args_json),
                },
                "result": json.loads(step.result_json),
            }
            for step in steps
        ],
    }

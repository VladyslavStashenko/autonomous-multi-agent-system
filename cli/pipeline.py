from __future__ import annotations

from difflib import SequenceMatcher
from pathlib import Path
from typing import Any
import re

from rich.live import Live
from rich.panel import Panel
from rich.spinner import Spinner
from rich.text import Text
from rich.tree import Tree

from agents import AutonomousAgent, ClientPool, Evaluator, OrchestratorAgent, Worker
from config import Settings
from ui.renderer import RICH_CONSOLE, format_error, render_chat_step, short_result
from ui.theme import Theme, color_line


def get_changed_line_numbers(old_content: str, new_content: str) -> set[int]:
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    matcher = SequenceMatcher(None, old_lines, new_lines)
    changed_lines: set[int] = set()
    for tag, _i1, _i2, j1, j2 in matcher.get_opcodes():
        if tag in {"replace", "insert"}:
            changed_lines.update(range(j1 + 1, j2 + 1))
    return changed_lines


def infer_task_language(task: str) -> str:
    return "uk" if re.search(r"[А-Яа-яІіЇїЄєҐґ]", task) else "en"


def generate_chat_summary(
    task: str,
    result: dict[str, Any],
    agent_type: str,
    settings: Settings,
    pool: ClientPool,
) -> str:
    task_language = infer_task_language(task)
    status = str(result.get("status", "unknown"))
    summary = str(result.get("summary", "")).strip()

    context: dict[str, Any] = {
        "agent_type": agent_type,
        "status": status,
        "summary": summary,
    }

    if agent_type == "multi":
        context["plan"] = result.get("plan", [])
        subtasks = result.get("subtasks", [])
        context["subtasks"] = [
            {
                "subtask": item.get("subtask", ""),
                "status": item.get("status", ""),
                "summary": item.get("summary", ""),
            }
            for item in subtasks
            if isinstance(item, dict)
        ]
    else:
        state = result.get("state", {}) if isinstance(result.get("state"), dict) else {}
        steps_history = state.get("steps_history", []) if isinstance(state.get("steps_history"), list) else []
        context["steps"] = [
            {
                "action": step.get("decision", {}).get("action", ""),
                "reason": step.get("decision", {}).get("reason", ""),
                "ok": step.get("result", {}).get("ok"),
                "message": short_result(step.get("result", {})),
            }
            for step in steps_history[-8:]
            if isinstance(step, dict)
        ]

    prompt = (
        "You are summarizing the completed work of a CLI coding agent for the end user.\n"
        f"Write in the exact same language as the user's task ({'Ukrainian' if task_language == 'uk' else 'English'}).\n"
        "Be concise: 2-4 sentences.\n"
        "Explain what was done, how it was done at a high level, and whether there were any errors, retries, or remaining issues.\n"
        "Do not roleplay, do not be sarcastic, do not use canned phrases, and do not invent facts.\n"
        "If the task failed or stopped early, say that clearly.\n\n"
        f"User task:\n{task}\n\n"
        f"Execution result:\n{context}"
    )
    response = pool.get_client().models.generate_content(
        model=settings.model,
        contents=prompt,
    )
    return (response.text or "").strip()


def run_pipeline(task: str, theme: Theme, mode: str, settings: Settings, agent_type: str, pool: ClientPool) -> str:
    worker = Worker()
    planner_model = settings.model
    coder_model = "gemini-2.5-flash-lite"
    evaluator = Evaluator(
        model=settings.model,
        max_attempts=settings.max_eval_attempts,
        client_getter=pool.get_client,
    )

    accent = theme.accent
    success = theme.success
    error = theme.error
    highlight = theme.highlight
    current_step = {"value": 0}
    planner_state: list[dict[str, Any]] = []

    def print_status_bar() -> None:
        if agent_type == "multi":
            model_label = f"planner/reviewer: {planner_model} | coder: {coder_model}"
        else:
            model_label = settings.model
        RICH_CONSOLE.print(
            Text(
                f"[{agent_type}] [{model_label}] [step {current_step['value']}/{settings.max_agent_steps}]",
                style=theme.ui_highlight,
            )
        )

    def print_planner_tree() -> None:
        tree = Tree(Text("[Planner]", style=theme.ui_highlight))
        for item in planner_state:
            marker = "✓" if item["done"] else "✗" if item["failed"] else "…"
            style = theme.ui_success if item["done"] else theme.ui_error if item["failed"] else theme.ui_accent
            tree.add(Text(f"{marker} {item['text']}", style=style))
        RICH_CONSOLE.print(tree)

    spinner_live: Live | None = None

    def pause_spinner() -> None:
        if spinner_live is not None:
            spinner_live.stop()

    def resume_spinner(message: str) -> None:
        if spinner_live is not None:
            spinner_live.update(Spinner("dots", text=message, style=theme.ui_accent), refresh=True)
            spinner_live.start()

    original_execute_step = worker.execute_step

    def execute_step_with_context(step: dict[str, Any]) -> dict[str, Any]:
        existed_before = False
        previous_content = ""
        if step.get("action") in {"write_file", "apply_patch"} and step.get("path"):
            file_path = Path(str(step["path"]))
            existed_before = file_path.exists()
            if existed_before:
                try:
                    previous_content = file_path.read_text(encoding="utf-8")
                except OSError:
                    previous_content = ""
        result = original_execute_step(step)
        if step.get("action") in {"write_file", "apply_patch"}:
            new_content = str(result.get("_display_content") or step.get("content") or "")
            changed_lines = (
                list(range(1, len(new_content.splitlines()) + 1))
                if not existed_before
                else sorted(get_changed_line_numbers(previous_content, new_content))
            )
            result = {
                **result,
                "_path_existed_before": existed_before,
                "_changed_lines": changed_lines,
            }
        return result

    worker.execute_step = execute_step_with_context

    def on_step(step_number: int, decision: dict[str, Any], result: dict[str, Any]) -> None:
        current_step["value"] = step_number
        action = decision.get("action", "unknown")
        reason = decision.get("reason", "")
        args = dict(decision.get("args", {}))
        if "_path_existed_before" in result:
            args["_path_existed_before"] = result["_path_existed_before"]
        if "_changed_lines" in result:
            args["_changed_lines"] = result["_changed_lines"]
        if reason:
            args["_reason"] = reason

        pause_spinner()
        if mode == "technical" and reason:
            RICH_CONSOLE.print(Text(f"Reason: {reason}", style=theme.ui_highlight))
        render_chat_step(action, args, result, theme)
        print_status_bar()
        resume_spinner("Agent is thinking about the next step...")

    def on_multi_stage(stage: str, payload: dict[str, Any]) -> None:
        pause_spinner()
        if stage == "planner":
            if payload.get("status") == "success":
                plan = payload.get("plan", [])
                planner_state.clear()
                planner_state.extend({"text": str(item), "done": False, "failed": False} for item in plan)
                print_planner_tree()
            else:
                RICH_CONSOLE.print(
                    Panel(
                        format_error(str(payload.get("error", "Unknown error."))),
                        title=" Planner ",
                        border_style=theme.ui_error,
                    )
                )
            print_status_bar()
            resume_spinner("Planner finished. Starting subtasks...")
            return
        if stage == "coder_start":
            subtask = str(payload.get("subtask", "")).strip()
            RICH_CONSOLE.print(
                Text(
                    f"[Coder] {payload.get('index', '?')}/{payload.get('total', '?')} {subtask}",
                    style=theme.ui_accent,
                )
            )
            print_status_bar()
            resume_spinner("Coder is working on the subtask...")
            return
        if stage == "coder_done":
            index = int(payload.get("index", 0)) - 1
            status = str(payload.get("status", "fail")).lower()
            if 0 <= index < len(planner_state):
                planner_state[index]["done"] = status == "done"
                planner_state[index]["failed"] = status != "done"
                print_planner_tree()
            summary = str(payload.get("summary", "")).strip()
            if summary:
                color = theme.ui_success if status == "done" else theme.ui_error
                RICH_CONSOLE.print(Text(summary, style=color))
            print_status_bar()
            resume_spinner("Preparing the next subtask...")
            return
        if stage == "coder_retry":
            reason = str(payload.get("reason", "")).strip()
            retry_message = f"Retry {payload.get('attempt', '?')} for subtask {payload.get('index', '?')}"
            if reason:
                retry_message = f"{retry_message}: {reason}"
            RICH_CONSOLE.print(Panel(retry_message, title=" Retry ", border_style=theme.ui_error))
            print_status_bar()
            resume_spinner("Retrying the subtask...")
            return
        if stage == "repair_start":
            RICH_CONSOLE.print(
                Text(f"[Repair {payload.get('cycle', '?')}] {payload.get('subtask', '')}", style=theme.ui_accent)
            )
            print_status_bar()
            resume_spinner("Repair cycle is running...")
            return
        if stage == "repair_done":
            message = str(payload.get("summary", "")).strip() or f"Cycle {payload.get('cycle', '?')} finished."
            RICH_CONSOLE.print(Panel(message, title=" Repair ", border_style=theme.ui_highlight))
            print_status_bar()
            resume_spinner("Reviewing the repair...")
            return
        if stage == "review_retry":
            message = f"Cycle {payload.get('cycle', '?')}, issues: {payload.get('issues_count', 0)}"
            RICH_CONSOLE.print(Panel(message, title=" Review Retry ", border_style=theme.ui_accent))
            print_status_bar()
            resume_spinner("Reviewer requested another pass...")
            return
        if stage == "pipeline_summary":
            summary_text = (
                f"status={payload.get('status', '?')} "
                f"subtasks={payload.get('total_subtasks', 0)} "
                f"coder_runs={payload.get('total_coder_runs', 0)} "
                f"review_cycles={payload.get('review_cycles', 0)} "
                f"retries={payload.get('retries_used', 0)}"
            )
            RICH_CONSOLE.print(Panel(summary_text, title=" Pipeline ", border_style=theme.ui_highlight))
            print_status_bar()
            resume_spinner("Finalizing the pipeline...")
            return
        if stage == "reviewer":
            reviewer_status = str(payload.get("status", "FAIL")).upper()
            reviewer_color = theme.ui_success if reviewer_status == "SUCCESS" else theme.ui_error
            message = str(payload.get("summary") or payload.get("error") or reviewer_status).strip()
            RICH_CONSOLE.print(
                Panel(message, title=f" Reviewer: {reviewer_status} ", border_style=reviewer_color)
            )
            print_status_bar()
            resume_spinner("Continuing after review...")

    if agent_type == "multi":
        agent = OrchestratorAgent(
            pool=pool,
            model=settings.model,
            worker=worker,
            evaluator=evaluator,
            max_steps=settings.max_agent_steps,
            on_step=on_step,
            on_stage=on_multi_stage,
            planner_model=planner_model,
            coder_model=coder_model,
            max_subtask_retries=1,
        )
    else:
        agent = AutonomousAgent(
            pool=pool,
            model=settings.model,
            worker=worker,
            evaluator=evaluator,
            max_steps=settings.max_agent_steps,
            on_step=on_step,
        )

    if mode == "technical":
        print()
        print(color_line(accent, f"Task: {task}"))
        print()
    else:
        print()

    spinner_live = Live(
        Spinner("dots", text="Agent is thinking...", style=theme.ui_accent),
        console=RICH_CONSOLE,
        refresh_per_second=12,
        transient=True,
    )
    with spinner_live:
        result = agent.run(task)
    summary = result.get("summary", "")
    task_language = infer_task_language(task)

    chat_summary = ""
    if mode != "technical":
        try:
            chat_summary = generate_chat_summary(task, result, agent_type, settings, pool)
        except Exception:
            chat_summary = ""
    fallback_chat_done = summary or ("Завдання успішно виконано." if task_language == "uk" else "Task completed successfully.")
    fallback_chat_fail = format_error(summary or ("Невідома помилка." if task_language == "uk" else "Unknown failure."))

    if mode != "technical" and result["status"] == "done":
        print()
        print(color_line(highlight, chat_summary or fallback_chat_done))
        print()
        return summary

    if mode != "technical" and result["status"] not in {"done", "max_steps"}:
        print()
        print(color_line(error, chat_summary or fallback_chat_fail))
        print()
        return summary

    if result["status"] == "done":
        if mode == "technical":
            print()
            print(color_line(highlight, f"  Done: {summary}"))
            print()
        else:
            print()
            if task_language == "uk":
                print(color_line(highlight, f"Готово. {summary}"))
            else:
                print(color_line(highlight, f"Done. {summary}"))
            print()
    elif result["status"] == "max_steps":
        if mode == "technical":
            print()
            print(color_line(error, f"Task stopped after reaching the step limit ({settings.max_agent_steps})."))
            if summary:
                print(color_line(error, format_error(summary)))
            print()
        else:
            print()
            stop_message = (
                f"Завдання зупинено після досягнення ліміту кроків ({settings.max_agent_steps})."
                if task_language == "uk"
                else f"Task stopped after reaching the step limit ({settings.max_agent_steps})."
            )
            print(color_line(error, chat_summary or stop_message))
            if summary and not chat_summary:
                print(color_line(error, format_error(summary)))
            print()
    else:
        if mode == "technical":
            print()
            print(color_line(error, f"Task failed: {format_error(summary or 'Unknown failure.')}"))
            print()
        else:
            print()
            if task_language == "uk":
                print(color_line(error, f"Знайшов проблему: {format_error(summary or 'Unknown failure.')}"))
            else:
                print(color_line(error, f"Found a problem: {format_error(summary or 'Unknown failure.')}"))
            print()
    return summary


def is_conversational(text: str) -> bool:
    text_lower = text.lower().strip()

    task_keywords = [
        "файл",
        "папк",
        "директор",
        "створи",
        "запусти",
        "прочитай",
        "видали",
        "напиши",
        ".py",
        ".txt",
        ".md",
        ".docx",
        "код",
        "скрипт",
        "file",
        "folder",
        "create",
        "run",
        "read",
        "delete",
        "write",
    ]

    if any(k in text_lower for k in task_keywords):
        return False

    triggers = [
        "привіт",
        "Привіт",
        "hello",
        "Hello",
        "Hi",
        "hi",
        "хто ти",
        "пока",
        "До побачення",
        "хто ти",
        "що ти вмієш",
        "що ти можеш",
        "як тебе звати",
        "розкажи про себе",
        "що ти робив",
        "попередня сесія",
        "що робив раніше",
        "що ти вже зробив",
        "пам'ятаєш",
        "минулого разу",
        "які тулзи",
        "які інструменти",
        "що ти взагалі",
        "хто ти взагалі",
        "ти взагалі",
        "who are you",
        "what can you",
        "what tools",
        "what are your tools",
        "tell me about yourself",
    ]

    return any(t in text_lower for t in triggers)

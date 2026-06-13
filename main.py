from __future__ import annotations

from datetime import datetime
from difflib import SequenceMatcher
import math
from pathlib import Path
import re
import shutil
import sys
import time
from dataclasses import dataclass, replace
from typing import Any

from colorama import Fore, Style as AnsiStyle, init
from prompt_toolkit.application import Application
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.layout import HSplit, Layout
from prompt_toolkit.layout.containers import VerticalAlign, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.styles import DynamicStyle, Style as PromptStyle
from prompt_toolkit.widgets import Frame, TextArea
from rich.console import Console, Group
from rich.live import Live
from rich.padding import Padding
from rich.panel import Panel
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.text import Text
from rich.tree import Tree

from agents import AutonomousAgent, ClientPool, Evaluator, OrchestratorAgent, Worker
from agents.memory import load_memory
from config import Settings, get_settings

sys.stdout.reconfigure(encoding="utf-8")


@dataclass(frozen=True)
class Theme:
    name: str
    accent: str
    success: str
    error: str
    highlight: str
    ui_accent: str
    ui_success: str
    ui_error: str
    ui_highlight: str
    frame_border: str
    input_bg: str
    input_fg: str
    cursor_fg: str
    cursor_bg: str


THEMES: dict[str, Theme] = {
    "cyan": Theme(
        name="cyan",
        accent=Fore.CYAN,
        success=Fore.GREEN,
        error=Fore.RED,
        highlight=Fore.YELLOW,
        ui_accent="#67e8f9",
        ui_success="#86efac",
        ui_error="#fca5a5",
        ui_highlight="#fde68a",
        frame_border="#4b5563",
        input_bg="#111111",
        input_fg="#ffffff",
        cursor_fg="#000000",
        cursor_bg="#ffffff",
    ),
    "green": Theme(
        name="green",
        accent=Fore.GREEN,
        success=Fore.GREEN,
        error=Fore.RED,
        highlight=Fore.CYAN,
        ui_accent="#86efac",
        ui_success="#86efac",
        ui_error="#fca5a5",
        ui_highlight="#67e8f9",
        frame_border="#3f5f3f",
        input_bg="#101510",
        input_fg="#eaffea",
        cursor_fg="#001100",
        cursor_bg="#8cff8c",
    ),
    "amber": Theme(
        name="amber",
        accent=Fore.YELLOW,
        success=Fore.GREEN,
        error=Fore.RED,
        highlight=Fore.MAGENTA,
        ui_accent="#fcd34d",
        ui_success="#86efac",
        ui_error="#fca5a5",
        ui_highlight="#f0abfc",
        frame_border="#6b5b2a",
        input_bg="#17140d",
        input_fg="#fff3d6",
        cursor_fg="#1a1200",
        cursor_bg="#ffd166",
    ),
}

SESSION_FILE = Path(__file__).resolve().parent / ".agent_state" / "session.json"
RICH_CONSOLE = Console()


def color_line(color: str, text: str) -> str:
    return f"{color}{text}{AnsiStyle.RESET_ALL}"


def mixed_color_line(parts: list[tuple[str, str]]) -> str:
    return "".join(f"{color}{text}{AnsiStyle.RESET_ALL}" for color, text in parts)


def clear_screen() -> None:
    print("\033[2J\033[H", end="")


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


def build_logo_lines(model_name: str) -> list[str]:
    logo_lines = [
        "",
        "     ██╗███████╗██████╗ ██╗███████╗",
        "     ██║██╔════╝██╔══██╗██║██╔════╝",
        "     ██║█████╗  ██║  ██║██║███████╗",
        "██   ██║██╔══╝  ██║  ██║██║╚════██║",
        "╚█████╔╝███████╗██████╔╝██║███████║",
        " ╚════╝ ╚══════╝╚═════╝ ╚═╝╚══════╝",
    ]
    info_lines = [
        "Tools",
        "  plan, files, commands",
        "",
        "Model",
        f"  {model_name}",
        "",
        "CLI Coding Agent v1.0.0",
        "Powered by Gemini",
    ]
    left_width = max(len(line) for line in logo_lines)
    right_width = max(len(line) for line in info_lines)
    total_width = left_width + 4 + right_width
    rendered = ["╭" + ("─" * (total_width + 2)) + "╮"]
    total_lines = max(len(logo_lines), len(info_lines))
    for i in range(total_lines):
        left = logo_lines[i] if i < len(logo_lines) else ""
        right = info_lines[i] if i < len(info_lines) else ""
        combined = f"{left.ljust(left_width)}    {right.ljust(right_width)}"
        rendered.append(f"│ {combined} │")
    rendered.append("╰" + ("─" * (total_width + 2)) + "╯")
    return rendered


def print_logo(model_name: str, theme: Theme) -> None:
    lines = build_logo_lines(model_name)
    body = Text("\n".join(lines), style=theme.ui_accent)
    subtitle = Text("jedis v1.0.0", style=theme.ui_highlight)
    padded_body = Padding(body, (0, 2, 0, 2))
    RICH_CONSOLE.print(Panel.fit(padded_body, border_style=theme.ui_accent, subtitle=subtitle))
    time.sleep(0.1)


def short_result(result: dict[str, Any]) -> str:
    if result.get("ok"):
        if result.get("stdout"):
            return f"stdout: {result['stdout']}"
        if result.get("content"):
            return f"content: {result['content']}"
        if result.get("items"):
            return f"items: {', '.join(result['items'])}"
        if result.get("message"):
            return str(result["message"])
        return "Done."
    return str(result.get("error") or result.get("stderr") or "Unknown error.")


def format_error(error_message: str) -> str:
    if "429" in error_message and "retryDelay" in error_message:
        match = re.search(r'"retryDelay":\s*"(\d+)s"', error_message)
        if match:
            seconds = match.group(1)
            return f"Request limit reached. Wait {seconds} seconds and try again."
    if "503" in error_message:
        return "Server is temporarily unavailable. Try again in a minute."
    if "RESOURCE_EXHAUSTED" in error_message and "Day" in error_message:
        return "Daily request limit exhausted. Try again tomorrow or use another API key."
    return error_message[:120]


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


def render_chat_step(action: str, args: dict[str, Any], result: dict[str, Any], theme: Theme) -> None:
    path = str(args.get("path") or result.get("path") or "").strip()
    command = str(args.get("command") or result.get("command") or "").strip()
    ok = bool(result.get("ok"))
    border_style = theme.ui_success if ok else theme.ui_error
    status_icon = "✓" if ok else "✗"

    def build_syntax_block(content: str, content_path: str, changed_lines: set[int] | None = None) -> Syntax:
        try:
            lexer = Syntax.guess_lexer(code=content, path=content_path or None)
        except Exception:
            lexer = None
        if not lexer and content_path:
            suffix = Path(content_path).suffix.lstrip(".")
            lexer = suffix or "text"
        syntax = Syntax(
            content,
            lexer or "text",
            word_wrap=True,
            line_numbers=True,
            highlight_lines=changed_lines or None,
        )
        content_lines = content.splitlines()
        for line_number in sorted(changed_lines or ()):
            if 1 <= line_number <= len(content_lines):
                syntax.stylize_range("on #1f4d3a", (line_number, 0), (line_number, len(content_lines[line_number - 1]) + 1))
        return syntax

    lines: list[Any] = []
    if path:
        icon = "📁" if action in {"list_directory", "delete_directory"} else "📄"
        lines.append(Text(f"{icon} {path}", style=theme.ui_accent))
    elif command:
        lines.append(Text(f"💻 {command}", style=theme.ui_accent))

    if command and path:
        lines.append(Text(f"💻 {command}", style=theme.ui_highlight))

    reason = str(args.get("_reason") or "").strip()
    if reason:
        lines.append(Text(f"Why: {reason}", style=theme.ui_highlight))

    if action == "run_command":
        status_message = str(
            result.get("message")
            or result.get("error")
            or result.get("stderr")
            or ("Command completed successfully." if ok else "Command failed.")
        ).strip()
    elif action == "read_file":
        status_message = str(
            result.get("message")
            or result.get("error")
            or ("File read successfully." if ok else "File read failed.")
        ).strip()
    else:
        status_message = str(
            result.get("message")
            or result.get("error")
            or result.get("stderr")
            or result.get("stdout")
            or short_result(result)
        ).strip()
    if not ok:
        status_message = format_error(status_message)
    lines.append(Text(f"{status_icon} {status_message}", style=border_style))

    if action == "list_directory" and result.get("items"):
        items = "\n".join(f"• {item}" for item in result["items"])
        lines.append(Text(items))

    if result.get("stdout"):
        lines.append(Text(str(result["stdout"])))
    if result.get("stderr") and result.get("stderr") != result.get("error"):
        lines.append(Text(str(result["stderr"]), style=theme.ui_error))

    code_or_content = str(result.get("_display_content") or result.get("content") or args.get("content") or "").strip()
    changed_lines_value = args.get("_changed_lines")
    changed_lines = {int(line) for line in changed_lines_value} if isinstance(changed_lines_value, list) else None
    if code_or_content:
        lines.append(build_syntax_block(code_or_content, path, changed_lines))

    panel = Panel(
        Group(*lines),
        title=f" {action} ",
        border_style=border_style,
        expand=True,
    )
    RICH_CONSOLE.print(panel)


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

def framed_input(style: PromptStyle) -> str:
    result = {"text": ""}

    input_area = TextArea(
        prompt="> ",
        multiline=True,
        wrap_lines=True,
        height=Dimension(min=1, preferred=1),
        dont_extend_height=True,
        style="class:input",
    )
    root = HSplit([Frame(input_area, style="class:frame")], align=VerticalAlign.TOP)

    kb = KeyBindings()

    def compute_visual_line_count(text: str, terminal_width: int) -> int:
        content_width = max(8, terminal_width - 6)
        first_line_width = max(1, content_width - 2)
        total = 0
        logical_lines = text.splitlines() or [""]

        for line in logical_lines:
            if not line:
                total += 1
                continue

            first_segment = 1
            remaining = max(0, len(line) - first_line_width)
            wrapped_segments = math.ceil(remaining / content_width) if remaining > 0 else 0
            total += first_segment + wrapped_segments

        return max(1, total)

    def refresh_input_height() -> None:
        terminal_width = shutil.get_terminal_size((80, 24)).columns
        input_area.window.height = Dimension.exact(
            compute_visual_line_count(input_area.text, terminal_width)
        )

    input_area.buffer.on_text_changed += lambda _: refresh_input_height()
    refresh_input_height()

    @kb.add("enter")
    def _(event) -> None:
        result["text"] = input_area.text
        event.app.exit()

    app = Application(
        layout=Layout(root),
        key_bindings=kb,
        style=style,
        full_screen=False,
        cursor=CursorShape.BLINKING_BEAM,
    )
    app.before_render += lambda _: refresh_input_height()
    app.run()
    return result["text"].strip()


def build_prompt_style(theme: Theme) -> PromptStyle:
    return PromptStyle.from_dict({
        "": "fg:#d8dee9 bg:#000000",
        "frame.border": f"fg:{theme.frame_border}",
        "frame.label": f"fg:{theme.frame_border}",
        "input": f"fg:{theme.input_fg} bg:{theme.input_bg}",
        "cursor": f"fg:{theme.cursor_fg} bg:{theme.cursor_bg}",
        "menu.title": f"fg:{theme.ui_highlight} bg:#000000 bold",
        "menu.item": "fg:#d8dee9 bg:#000000",
        "menu.selected": f"fg:{theme.ui_highlight} bg:#000000 bold",
        "menu.preview": f"fg:{theme.ui_accent} bg:#000000",
        "menu.preview-ok": f"fg:{theme.ui_success} bg:#000000",
        "menu.preview-bad": f"fg:{theme.ui_error} bg:#000000",
    })


def print_help(theme: Theme) -> None:
    print()
    print(color_line(theme.accent, "Commands"))
    print(color_line(theme.accent, "  /help            Show available commands"))
    print(color_line(theme.accent, "  /clear           Clear memory and agent state"))
    print(color_line(theme.accent, "  /config          Show current settings"))
    print(color_line(theme.accent, "  /config model    Choose model for current session"))
    print(color_line(theme.accent, "  /config steps    Choose max agent steps for current session"))
    print(color_line(theme.accent, "  /history         Show last 5 memory entries"))
    print(color_line(theme.accent, "  /history <n>     Show last N memory entries"))
    print(color_line(theme.accent, "  /mode            Show current output mode"))
    print(color_line(theme.accent, "  /mode <name>     Switch output mode"))
    print(color_line(theme.accent, "  /agent           Show current agent mode"))
    print(color_line(theme.accent, "  /agent <type>    Switch agent mode"))
    print(color_line(theme.accent, "  /theme           Pick theme with arrow keys"))
    print(color_line(theme.accent, "  /theme <name>    Switch theme directly"))
    print(color_line(theme.accent, "  exit             Close the agent"))
    print()


def choose_option(
    title: str,
    items: list[tuple[str, str]],
    default_key: str,
    get_preview_theme,
) -> str | None:
    state = {"index": next((i for i, item in enumerate(items) if item[0] == default_key), 0), "result": None}

    def render_menu():
        preview_theme = get_preview_theme(state["index"])
        fragments: list[tuple[str, str]] = [
            ("class:menu.title", f"{title}\n\n"),
        ]
        for idx, (_, label) in enumerate(items, 1):
            prefix = "❯ " if idx - 1 == state["index"] else "  "
            style = "class:menu.selected" if idx - 1 == state["index"] else "class:menu.item"
            suffix = " ✓" if idx - 1 == state["index"] else ""
            fragments.append((style, f"{prefix}{idx}. {label}{suffix}\n"))
        fragments.extend([
            ("", "\n"),
            ("class:menu.preview", f"Preview theme: {preview_theme.name}\n"),
            ("class:menu.preview", "Sample: Planning file and command steps\n"),
            ("class:menu.preview-ok", "Sample: [OK] Command completed successfully\n"),
            ("class:menu.preview-bad", "Sample: [FAIL] Step needs retry\n"),
            ("class:menu.item", "\nUse ↑/↓ to browse and Enter to confirm."),
        ])
        return fragments

    kb = KeyBindings()

    @kb.add("up")
    def _(event) -> None:
        state["index"] = (state["index"] - 1) % len(items)
        event.app.invalidate()

    @kb.add("down")
    def _(event) -> None:
        state["index"] = (state["index"] + 1) % len(items)
        event.app.invalidate()

    @kb.add("enter")
    def _(event) -> None:
        state["result"] = items[state["index"]][0]
        event.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    def _(event) -> None:
        event.app.exit()

    body = Window(FormattedTextControl(render_menu), always_hide_cursor=True)
    frame = Frame(body, style="class:frame")
    app = Application(
        layout=Layout(frame),
        key_bindings=kb,
        style=DynamicStyle(lambda: build_prompt_style(get_preview_theme(state["index"]))),
        full_screen=False,
        cursor=CursorShape.BLINKING_BEAM,
    )
    app.run()
    return state["result"]


def handle_command(
    user_input: str,
    theme: Theme,
    mode: str,
    agent_type: str,
    base_settings: Settings,
    config_overrides: dict[str, Any],
) -> tuple[bool, Theme, str, str, dict[str, Any]]:
    command = user_input.strip()
    if command == "/help":
        print_help(theme)
        return True, theme, mode, agent_type, config_overrides

    if command == "/clear":
        print()
        confirmation = input("Clear memory and agent state? (y/n) ").strip().lower()
        if confirmation == "y":
            memory_file = Path(__file__).resolve().parent / ".agent_memory" / "memory.json"
            state_file = Path(__file__).resolve().parent / ".agent_state" / "last_run.json"
            session_file = SESSION_FILE
            if memory_file.exists():
                memory_file.unlink()
            if state_file.exists():
                state_file.unlink()
            if session_file.exists():
                session_file.unlink()
            print(color_line(theme.highlight, "Memory cleared."))
        else:
            print(color_line(theme.accent, "Cancelled."))
        print()
        return True, theme, mode, agent_type, config_overrides

    if command == "/config":
        settings = get_effective_settings(base_settings, config_overrides)
        print()
        print(color_line(theme.accent, f"model: {settings.model}"))
        print(color_line(theme.accent, f"max_agent_steps: {settings.max_agent_steps}"))
        print(color_line(theme.accent, f"current mode: {mode}"))
        print(color_line(theme.accent, f"current agent mode: {agent_type}"))
        print(color_line(theme.accent, f"current theme: {theme.name}"))
        print()
        return True, theme, mode, agent_type, config_overrides

    if command == "/config model":
        settings = get_effective_settings(base_settings, config_overrides)
        selected = choose_option(
            title="Choose model:",
            items=[
                ("gemini-2.5-flash-lite", "gemini-2.5-flash-lite"),
                ("gemini-2.5-flash", "gemini-2.5-flash"),
                ("gemini-2.5-pro", "gemini-2.5-pro"),
            ],
            default_key=settings.model,
            get_preview_theme=lambda _: theme,
        )
        if selected is None:
            return True, theme, mode, agent_type, config_overrides
        next_overrides = dict(config_overrides)
        next_overrides["model"] = selected
        save_session(build_session_state(base_settings, next_overrides, theme, mode, agent_type))
        print()
        print(mixed_color_line([
            ("", "Model switched to "),
            (theme.accent, selected),
        ]))
        clear_screen()
        print_logo(selected, theme)
        return True, theme, mode, agent_type, next_overrides

    if command == "/config steps":
        settings = get_effective_settings(base_settings, config_overrides)
        selected = choose_option(
            title="Choose max agent steps:",
            items=[
                ("5", "5"),
                ("10", "10"),
                ("15", "15"),
                ("20", "20"),
                ("30", "30"),
            ],
            default_key=str(settings.max_agent_steps),
            get_preview_theme=lambda _: theme,
        )
        if selected is None:
            return True, theme, mode, agent_type, config_overrides
        next_overrides = dict(config_overrides)
        next_overrides["max_agent_steps"] = int(selected)
        save_session(build_session_state(base_settings, next_overrides, theme, mode, agent_type))
        print()
        print(mixed_color_line([
            ("", "Max agent steps switched to "),
            (theme.accent, selected),
        ]))
        return True, theme, mode, agent_type, next_overrides

    if command == "/history" or command.startswith("/history "):
        limit = 5
        if command.startswith("/history "):
            count_text = command.split(maxsplit=1)[1].strip()
            try:
                limit = int(count_text)
                if limit <= 0:
                    raise ValueError
            except ValueError:
                print()
                print(color_line(theme.error, f"Invalid history count: {count_text}"))
                return True, theme, mode, agent_type, config_overrides

        memory = load_memory()
        entries = memory.get("entries", [])
        print()
        if not entries:
            print(color_line(theme.accent, "No history entries found."))
            print()
            return True, theme, mode, agent_type, config_overrides

        for entry in entries[-limit:]:
            timestamp = str(entry.get("timestamp", "unknown"))
            status = str(entry.get("status", "fail"))
            task = str(entry.get("task", "")).strip()
            if len(task) > 60:
                task = task[:60] + "..."
            color = theme.highlight if status == "done" else theme.error
            print(color_line(color, f"[{timestamp}] {status}: {task}"))
        print()
        return True, theme, mode, agent_type, config_overrides

    if command == "/mode":
        selected = choose_option(
            title="Choose output mode:",
            items=[
                ("technical", "Technical — raw agent log"),
                ("chat", "Chat — human-friendly phrases"),
            ],
            default_key=mode,
            get_preview_theme=lambda _: theme,
        )
        if selected is None:
            return True, theme, mode, agent_type, config_overrides
        print()
        print(mixed_color_line([
            ("", "Mode switched to "),
            (theme.accent, selected),
        ]))
        save_session(build_session_state(base_settings, config_overrides, theme, selected, agent_type))
        return True, theme, selected, agent_type, config_overrides

    if command.startswith("/mode "):
        selected = command.split(maxsplit=1)[1].strip().lower()
        if selected in {"technical", "chat"}:
            print()
            print(mixed_color_line([
                ("", "Mode switched to "),
                (theme.accent, selected),
            ]))
            save_session(build_session_state(base_settings, config_overrides, theme, selected, agent_type))
            return True, theme, selected, agent_type, config_overrides
        print()
        print(color_line(theme.error, f"Unknown mode: {selected}"))
        print(color_line(theme.accent, "Available modes: technical, chat"))
        return True, theme, mode, agent_type, config_overrides

    if command == "/agent":
        selected = choose_option(
            title="Choose agent mode:",
            items=[
                ("single", "Single - current autonomous agent"),
                ("multi", "Multi - planner, coder, reviewer"),
            ],
            default_key=agent_type,
            get_preview_theme=lambda _: theme,
        )
        if selected is None:
            return True, theme, mode, agent_type, config_overrides
        print()
        print(mixed_color_line([
            ("", "Agent mode switched to "),
            (theme.accent, selected.upper()),
        ]))
        save_session(build_session_state(base_settings, config_overrides, theme, mode, selected))
        return True, theme, mode, selected, config_overrides

    if command.startswith("/agent "):
        selected = command.split(maxsplit=1)[1].strip().lower()
        if selected in {"single", "multi"}:
            print()
            print(mixed_color_line([
                ("", "Agent mode switched to "),
                (theme.accent, selected.upper()),
            ]))
            save_session(build_session_state(base_settings, config_overrides, theme, mode, selected))
            return True, theme, mode, selected, config_overrides
        print()
        print(color_line(theme.error, f"Unknown agent mode: {selected}"))
        print(color_line(theme.accent, "Available agent modes: single, multi"))
        return True, theme, mode, agent_type, config_overrides

    if command == "/theme":
        selected = choose_option(
            title="Choose the theme that looks best in your terminal:",
            items=[(name, name.title()) for name in THEMES],
            default_key=theme.name,
            get_preview_theme=lambda idx: THEMES[list(THEMES.keys())[idx]],
        )
        if selected is None:
            return True, theme, mode, agent_type, config_overrides
        next_theme = THEMES[selected]
        print()
        print(mixed_color_line([
            ("", "Theme switched to "),
            (next_theme.accent, next_theme.name),
        ]))
        save_session(build_session_state(base_settings, config_overrides, next_theme, mode, agent_type))
        return True, next_theme, mode, agent_type, config_overrides

    if command.startswith("/theme "):
        selected = command.split(maxsplit=1)[1].strip().lower()
        if selected in THEMES:
            next_theme = THEMES[selected]
            print()
            print(mixed_color_line([
                ("", "Theme switched to "),
                (next_theme.accent, next_theme.name),
            ]))
            save_session(build_session_state(base_settings, config_overrides, next_theme, mode, agent_type))
            return True, next_theme, mode, agent_type, config_overrides
        print()
        print(color_line(theme.error, f"Unknown theme: {selected}"))
        print(color_line(theme.accent, f"Available themes: {', '.join(THEMES)}"))
        return True, theme, mode, agent_type, config_overrides

    return False, theme, mode, agent_type, config_overrides


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


def main() -> None:
    init(autoreset=False)
    settings = get_settings()
    client_pool = ClientPool(settings.api_keys)
    session = load_session()
    config_overrides: dict[str, Any] = {}
    if isinstance(session.get("model"), str) and session["model"] in {
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
    }:
        config_overrides["model"] = session["model"]
    if isinstance(session.get("max_agent_steps"), int) and session["max_agent_steps"] in {5, 10, 15, 20, 30}:
        config_overrides["max_agent_steps"] = session["max_agent_steps"]
    current_theme = THEMES.get(str(session.get("theme", "cyan")), THEMES["cyan"])
    current_mode = str(session.get("mode", "technical"))
    if current_mode not in {"technical", "chat"}:
        current_mode = "technical"
    current_agent_type = str(session.get("agent_type", "single")).lower()
    if current_agent_type not in {"single", "multi"}:
        current_agent_type = "single"
    effective_settings = get_effective_settings(settings, config_overrides)
    clear_screen()
    print_logo(effective_settings.model, current_theme)

    while True:
        style = build_prompt_style(current_theme)
        user_input = framed_input(style)

        if user_input.lower() in ["exit", "вихід", "quit"]:
            save_session(build_session_state(settings, config_overrides, current_theme, current_mode, current_agent_type))
            print(color_line(current_theme.accent, "Shutting down. May the Force be with you."))
            break
        if not user_input:
            continue
        if user_input.startswith("/"):
            handled, current_theme, current_mode, current_agent_type, config_overrides = handle_command(
                user_input,
                current_theme,
                current_mode,
                current_agent_type,
                settings,
                config_overrides,
            )
            if handled:
                continue
            print()
            print(color_line(current_theme.error, f"Unknown command: {user_input.strip()}"))
            print(color_line(current_theme.accent, "Use /help to see available commands."))
            print()
            continue
        try:
            effective_settings = get_effective_settings(settings, config_overrides)
            if is_conversational(user_input):
                memory = load_memory()
                last = memory.get("entries", [])[-1] if memory.get("entries") else None
                memory_context = f"Last session: {last}" if last else "No previous sessions."
                prompt = (
                    "You MUST respond in the exact same language as the user's message. If Ukrainian — respond in Ukrainian. If English — respond in English. No exceptions. "
                    "You are JEDIS — a sarcastic, grumpy but competent CLI agent. "
                    "Answer the user's question in character without introducing yourself every time. "
                    "If asked who you are — introduce yourself once briefly. "
                    "If asked what you can do — list tools sarcastically without saying your name. "
                    "If asked how you work — explain sarcastically without saying your name. "
                    "Your actual tools are: read_file, write_file, apply_patch, list_directory, delete_directory, run_command, run_interactive_command, write_docx. "
                    "When asked about tools — mention only these, sarcastically. Do not invent other tools. "
                    "Respond in the same language as the user. Be brief, 2-3 sentences max. "
                    f"{memory_context}"
                )
                response = client_pool.get_client().models.generate_content(
                    model=effective_settings.model,
                    contents=[prompt, user_input],
                )
                print()
                print(color_line(current_theme.highlight, (response.text or "").strip()))
                print()
                continue
            run_pipeline(user_input, current_theme, current_mode, effective_settings, current_agent_type, client_pool)
        except KeyboardInterrupt:
            print()
            print(color_line(current_theme.error, "Session stopped by user."))
            print()
        except Exception as exc:
            print(color_line(current_theme.error, f"❌ Error: {exc}"))


if __name__ == "__main__":
    main()

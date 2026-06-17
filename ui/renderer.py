from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from .theme import Theme

RICH_CONSOLE = Console()


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


def render_chat_step(action: str, args: dict[str, Any], result: dict[str, Any], theme: Theme, language: str = "en") -> None:
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
        lines.append(Text(f"{'Чому' if language == 'uk' else 'Why'}: {reason}", style=theme.ui_highlight))

    if action == "run_command":
        status_message = str(
            result.get("message")
            or result.get("error")
            or result.get("stderr")
            or ("Команду успішно виконано." if ok and language == "uk" else "Command completed successfully." if ok else "Помилка виконання команди." if language == "uk" else "Command failed.")
        ).strip()
    elif action == "read_file":
        status_message = str(
            result.get("message")
            or result.get("error")
            or ("Файл успішно прочитано." if ok and language == "uk" else "File read successfully." if ok else "Не вдалося прочитати файл." if language == "uk" else "File read failed.")
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


def clear_screen() -> None:
    print("\033[2J\033[H", end="")

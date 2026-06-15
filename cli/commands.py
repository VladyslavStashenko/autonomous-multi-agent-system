from __future__ import annotations

from pathlib import Path
from typing import Any

from agents.memory import load_memory
from config import Settings
from session import SESSION_FILE, build_session_state, get_effective_settings, save_session
from ui.input import choose_option
from ui.logo import print_logo
from ui.renderer import clear_screen
from ui.theme import THEMES, Theme, color_line, mixed_color_line


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
            memory_file = Path(__file__).resolve().parent.parent / ".agent_memory" / "memory.json"
            state_file = Path(__file__).resolve().parent.parent / ".agent_state" / "last_run.json"
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

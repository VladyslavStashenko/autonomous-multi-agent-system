from __future__ import annotations

import sys
from typing import Any

from colorama import init

from agents import ClientPool
from agents.memory import load_memory
from cli.commands import handle_command
from cli.pipeline import is_conversational, run_pipeline
from config import get_settings
from session import build_session_state, get_effective_settings, load_session, save_session
from storage.database import init_db
from ui.input import framed_input
from ui.logo import print_logo
from ui.renderer import clear_screen
from ui.theme import THEMES, build_prompt_style, color_line


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    init(autoreset=False)
    init_db()
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

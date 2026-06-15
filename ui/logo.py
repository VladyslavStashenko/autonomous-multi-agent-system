from __future__ import annotations

import time

from rich.padding import Padding
from rich.panel import Panel
from rich.text import Text

from .renderer import RICH_CONSOLE
from .theme import Theme


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

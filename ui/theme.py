from __future__ import annotations

from dataclasses import dataclass

from colorama import Fore, Style as AnsiStyle
from prompt_toolkit.styles import Style as PromptStyle


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


def color_line(color: str, text: str) -> str:
    return f"{color}{text}{AnsiStyle.RESET_ALL}"


def mixed_color_line(parts: list[tuple[str, str]]) -> str:
    return "".join(f"{color}{text}{AnsiStyle.RESET_ALL}" for color, text in parts)


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

from __future__ import annotations

import math
import shutil

from prompt_toolkit.application import Application
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout
from prompt_toolkit.layout.containers import VerticalAlign, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.layout.dimension import Dimension
from prompt_toolkit.styles import DynamicStyle, Style as PromptStyle
from prompt_toolkit.widgets import Frame, TextArea

from .theme import build_prompt_style


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

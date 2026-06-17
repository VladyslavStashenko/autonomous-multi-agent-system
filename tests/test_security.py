from __future__ import annotations

from pathlib import Path

import pytest

from tools import security


def test_safe_path_allows_path_inside_project_root(
    isolated_project_root: Path,
) -> None:
    nested = isolated_project_root / "folder" / "file.txt"
    nested.parent.mkdir(parents=True)
    nested.write_text("ok", encoding="utf-8")

    resolved = security.safe_path("folder/file.txt")

    assert resolved == nested.resolve()


def test_safe_path_blocks_path_traversal(isolated_project_root: Path) -> None:
    with pytest.raises(ValueError, match="Path escapes project root"):
        security.safe_path("../../etc/passwd")


@pytest.mark.parametrize("command", ["rm -rf /", "format c:", "sudo shutdown now"])
def test_is_command_safe_blocks_dangerous_commands(command: str) -> None:
    is_safe, reason = security.is_command_safe(command)

    assert is_safe is False
    assert reason is not None


def test_is_command_safe_allows_safe_command() -> None:
    is_safe, reason = security.is_command_safe("python script.py")

    assert is_safe is True
    assert reason is None

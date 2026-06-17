from __future__ import annotations

import builtins
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from tools import filesystem


def test_write_file_creates_new_file(isolated_project_root: Path) -> None:
    result = filesystem.write_file("new.txt", "hello")

    assert result["ok"] is True
    assert result["path"] == str((isolated_project_root / "new.txt").resolve())
    assert (isolated_project_root / "new.txt").read_text(encoding="utf-8") == "hello"


def test_write_file_overwrites_existing_file(isolated_project_root: Path) -> None:
    target = isolated_project_root / "existing.txt"
    target.write_text("old", encoding="utf-8")

    result = filesystem.write_file("existing.txt", "new")

    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "new"


def test_read_file_returns_content_for_existing_file(isolated_project_root: Path) -> None:
    target = isolated_project_root / "readme.txt"
    target.write_text("read content", encoding="utf-8")

    result = filesystem.read_file("readme.txt")

    assert result == {
        "ok": True,
        "path": str(target.resolve()),
        "content": "read content",
    }


def test_read_file_returns_error_when_file_missing() -> None:
    result = filesystem.read_file("missing.txt")

    assert result["ok"] is False
    assert "File does not exist" in result["error"]


def test_append_file_appends_to_existing_file(isolated_project_root: Path) -> None:
    target = isolated_project_root / "append.txt"
    target.write_text("hello", encoding="utf-8")

    result = filesystem.append_file("append.txt", " world")

    assert result["ok"] is True
    assert target.read_text(encoding="utf-8") == "hello world"


def test_append_file_creates_file_when_missing(isolated_project_root: Path) -> None:
    result = filesystem.append_file("created.txt", "content")

    assert result["ok"] is True
    assert (isolated_project_root / "created.txt").read_text(encoding="utf-8") == "content"


def test_apply_patch_replaces_unique_text(isolated_project_root: Path) -> None:
    target = isolated_project_root / "patch.txt"
    target.write_text("hello old world", encoding="utf-8")

    result = filesystem.apply_patch(
        "patch.txt",
        [{"old_text": "old", "new_text": "new"}],
    )

    assert result["ok"] is True
    assert result["message"] == "Patch applied successfully."
    assert target.read_text(encoding="utf-8") == "hello new world"


def test_apply_patch_returns_error_when_file_missing() -> None:
    result = filesystem.apply_patch(
        "missing.txt",
        [{"old_text": "a", "new_text": "b"}],
    )

    assert result["ok"] is False
    assert "File does not exist" in result["error"]


def test_apply_patch_returns_error_for_empty_patches(isolated_project_root: Path) -> None:
    target = isolated_project_root / "patch.txt"
    target.write_text("content", encoding="utf-8")

    result = filesystem.apply_patch("patch.txt", [])

    assert result["ok"] is False
    assert "non-empty patches list" in result["error"]


def test_apply_patch_returns_error_when_old_text_missing(isolated_project_root: Path) -> None:
    target = isolated_project_root / "patch.txt"
    target.write_text("content", encoding="utf-8")

    result = filesystem.apply_patch(
        "patch.txt",
        [{"old_text": "missing", "new_text": "new"}],
    )

    assert result["ok"] is False
    assert "old_text was not found" in result["error"]


def test_apply_patch_returns_error_when_old_text_is_ambiguous(isolated_project_root: Path) -> None:
    target = isolated_project_root / "patch.txt"
    target.write_text("repeat repeat", encoding="utf-8")

    result = filesystem.apply_patch(
        "patch.txt",
        [{"old_text": "repeat", "new_text": "new"}],
    )

    assert result["ok"] is False
    assert "ambiguous" in result["error"]


def test_apply_patch_reports_no_changes_when_content_unchanged(isolated_project_root: Path) -> None:
    target = isolated_project_root / "patch.txt"
    target.write_text("same", encoding="utf-8")

    result = filesystem.apply_patch(
        "patch.txt",
        [{"old_text": "same", "new_text": "same"}],
    )

    assert result["ok"] is True
    assert result["message"] == "Patch made no changes."


def test_list_directory_returns_sorted_items(isolated_project_root: Path) -> None:
    (isolated_project_root / "b.txt").write_text("b", encoding="utf-8")
    (isolated_project_root / "a.txt").write_text("a", encoding="utf-8")
    (isolated_project_root / "folder").mkdir()

    result = filesystem.list_directory(".")

    assert result["ok"] is True
    assert result["items"] == ["a.txt", "b.txt", "folder"]


def test_list_directory_returns_error_when_missing() -> None:
    result = filesystem.list_directory("missing-dir")

    assert result["ok"] is False
    assert "Directory does not exist" in result["error"]


def test_list_directory_returns_error_for_file_path(isolated_project_root: Path) -> None:
    (isolated_project_root / "file.txt").write_text("x", encoding="utf-8")

    result = filesystem.list_directory("file.txt")

    assert result["ok"] is False
    assert "Path is not a directory" in result["error"]


def test_delete_directory_removes_existing_directory(
    isolated_project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_project_root / "to-delete"
    target.mkdir()
    (target / "nested.txt").write_text("x", encoding="utf-8")
    monkeypatch.setattr(filesystem, "ensure_not_project_root", lambda path: None)

    result = filesystem.delete_directory("to-delete")

    assert result["ok"] is True
    assert not target.exists()


def test_delete_directory_returns_error_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(filesystem, "ensure_not_project_root", lambda path: None)

    result = filesystem.delete_directory("missing-dir")

    assert result["ok"] is False
    assert "Directory does not exist" in result["error"]


def test_delete_directory_returns_error_for_file_path(
    isolated_project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = isolated_project_root / "file.txt"
    target.write_text("x", encoding="utf-8")
    monkeypatch.setattr(filesystem, "ensure_not_project_root", lambda path: None)

    result = filesystem.delete_directory("file.txt")

    assert result["ok"] is False
    assert "Path is not a directory" in result["error"]


def test_run_command_returns_reason_for_unsafe_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (False, "blocked"))

    result = filesystem.run_command("rm -rf /")

    assert result == {"ok": False, "error": "blocked"}


def test_run_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (True, None))
    monkeypatch.setattr(filesystem.platform, "system", lambda: "Windows")
    monkeypatch.setattr(
        filesystem.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="ok\n", stderr=""),
    )

    result = filesystem.run_command("python app.py")

    assert result["ok"] is True
    assert result["command"] == "python app.py"
    assert result["stdout"] == "ok"


def test_run_command_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (True, None))
    monkeypatch.setattr(
        filesystem.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(cmd="python", timeout=60)
        ),
    )

    result = filesystem.run_command("python app.py")

    assert result == {"ok": False, "error": "Command timed out after 60 seconds"}


def test_run_command_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (True, None))
    monkeypatch.setattr(
        filesystem.subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = filesystem.run_command("python app.py")

    assert result["ok"] is False
    assert "run_command failed: boom" == result["error"]


def test_run_interactive_command_returns_reason_for_unsafe_command(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (False, "blocked"))

    result = filesystem.run_interactive_command("rm -rf /")

    assert result == {"ok": False, "error": "blocked"}


def test_run_interactive_command_success(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock()
    process.returncode = 0
    process.wait.return_value = None
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (True, None))
    monkeypatch.setattr(filesystem.subprocess, "Popen", lambda *args, **kwargs: process)

    result = filesystem.run_interactive_command("python app.py")

    assert result["ok"] is True
    assert result["command"] == "python app.py"
    assert result["message"] == "Command completed."


def test_run_interactive_command_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    process = MagicMock()
    process.wait.side_effect = subprocess.TimeoutExpired(cmd="python", timeout=60)
    process.kill = MagicMock()
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (True, None))
    monkeypatch.setattr(filesystem.subprocess, "Popen", lambda *args, **kwargs: process)

    result = filesystem.run_interactive_command("python app.py")

    assert result == {"ok": False, "error": "Command timed out after 60 seconds"}
    process.kill.assert_called_once()


def test_run_interactive_command_generic_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(filesystem, "is_command_safe", lambda command: (True, None))
    monkeypatch.setattr(
        filesystem.subprocess,
        "Popen",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    result = filesystem.run_interactive_command("python app.py")

    assert result["ok"] is False
    assert "run_interactive_command failed: boom" == result["error"]


def test_write_docx_returns_error_on_import_error(monkeypatch: pytest.MonkeyPatch) -> None:
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "docx":
            raise ImportError("missing")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = filesystem.write_docx("report.docx", "hello")

    assert result["ok"] is False
    assert "python-docx is not installed" in result["error"]


def test_write_docx_success_with_mocked_document(
    isolated_project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    saved_paths: list[str] = []
    paragraphs: list[str] = []

    class FakeDocument:
        def add_paragraph(self, text: str) -> None:
            paragraphs.append(text)

        def save(self, path: str) -> None:
            saved_paths.append(path)

    fake_docx_module = SimpleNamespace(Document=FakeDocument)
    monkeypatch.setitem(sys.modules, "docx", fake_docx_module)

    result = filesystem.write_docx("report.docx", "line1\n\nline2")

    assert result["ok"] is True
    assert result["path"] == str((isolated_project_root / "report.docx").resolve())
    assert saved_paths == [str((isolated_project_root / "report.docx").resolve())]
    assert paragraphs == ["line1", "line2"]

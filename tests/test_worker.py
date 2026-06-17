from __future__ import annotations

from pathlib import Path

import pytest

import agents.worker as worker_module
from agents.worker import Worker


def test_read_file_returns_expected_content(isolated_project_root: Path) -> None:
    sample_file = isolated_project_root / "sample.txt"
    sample_file.write_text("hello worker", encoding="utf-8")

    result = Worker().execute_step({"action": "read_file", "path": "sample.txt"})

    assert result["ok"] is True
    assert result["content"] == "hello worker"


def test_write_file_creates_file_with_content(isolated_project_root: Path) -> None:
    result = Worker().execute_step(
        {"action": "write_file", "path": "created.txt", "content": "created content"}
    )

    assert result["ok"] is True
    assert (isolated_project_root / "created.txt").read_text(encoding="utf-8") == "created content"


def test_unknown_action_returns_error() -> None:
    result = Worker().execute_step({"action": "unknown_action"})

    assert result["ok"] is False
    assert "Unknown action" in result["error"]


def test_repeated_read_uses_cache(isolated_project_root: Path) -> None:
    cached_file = isolated_project_root / "cached.txt"
    cached_file.write_text("cached content", encoding="utf-8")
    worker = Worker()

    first_result = worker.execute_step({"action": "read_file", "path": "cached.txt"})
    second_result = worker.execute_step({"action": "read_file", "path": "cached.txt"})

    assert first_result["ok"] is True
    assert "_from_cache" not in first_result
    assert second_result["ok"] is True
    assert second_result["_from_cache"] is True
    assert second_result["content"] == "cached content"


def test_write_file_invalidates_read_cache(isolated_project_root: Path) -> None:
    cached_file = isolated_project_root / "cached.txt"
    cached_file.write_text("before", encoding="utf-8")
    worker = Worker()

    worker.execute_step({"action": "read_file", "path": "cached.txt"})
    write_result = worker.execute_step(
        {"action": "write_file", "path": "cached.txt", "content": "after"}
    )
    read_after_write = worker.execute_step({"action": "read_file", "path": "cached.txt"})

    assert write_result["ok"] is True
    assert read_after_write["ok"] is True
    assert "_from_cache" not in read_after_write
    assert read_after_write["content"] == "after"


def test_repeated_list_directory_uses_cache(isolated_project_root: Path) -> None:
    (isolated_project_root / "folder").mkdir()
    (isolated_project_root / "folder" / "a.txt").write_text("a", encoding="utf-8")
    worker = Worker()

    first_result = worker.execute_step({"action": "list_directory", "path": "folder"})
    second_result = worker.execute_step({"action": "list_directory", "path": "folder"})

    assert first_result["ok"] is True
    assert "_from_cache" not in first_result
    assert second_result["ok"] is True
    assert second_result["_from_cache"] is True


def test_write_file_invalidates_parent_list_directory_cache(isolated_project_root: Path) -> None:
    folder = isolated_project_root / "folder"
    folder.mkdir()
    (folder / "file.txt").write_text("before", encoding="utf-8")
    worker = Worker()

    worker.execute_step({"action": "list_directory", "path": "folder"})
    worker.execute_step({"action": "write_file", "path": "folder/file.txt", "content": "after"})
    list_after_write = worker.execute_step({"action": "list_directory", "path": "folder"})

    assert list_after_write["ok"] is True
    assert "_from_cache" not in list_after_write


def test_delete_directory_invalidates_directory_cache(
    isolated_project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    folder = isolated_project_root / "folder"
    folder.mkdir()
    (folder / "file.txt").write_text("before", encoding="utf-8")
    worker = Worker()
    monkeypatch.setattr(worker_module, "TOOL_REGISTRY", {**worker_module.TOOL_REGISTRY})

    worker.execute_step({"action": "list_directory", "path": "folder"})
    delete_result = worker.execute_step({"action": "delete_directory", "path": "folder"})
    list_after_delete = worker.execute_step({"action": "list_directory", "path": "folder"})

    assert delete_result["ok"] is True
    assert list_after_delete["ok"] is False
    assert "_from_cache" not in list_after_delete


def test_apply_patch_invalidates_read_cache(isolated_project_root: Path) -> None:
    target = isolated_project_root / "patch.txt"
    target.write_text("before", encoding="utf-8")
    worker = Worker()

    worker.execute_step({"action": "read_file", "path": "patch.txt"})
    worker.execute_step(
        {
            "action": "apply_patch",
            "path": "patch.txt",
            "patches": [{"old_text": "before", "new_text": "after"}],
        }
    )
    read_after_patch = worker.execute_step({"action": "read_file", "path": "patch.txt"})

    assert read_after_patch["ok"] is True
    assert "_from_cache" not in read_after_patch
    assert read_after_patch["content"] == "after"


def test_unsupported_action_signature_returns_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(worker_module, "TOOL_REGISTRY", {"custom_action": lambda *args, **kwargs: {"ok": True}})
    worker = Worker()

    result = worker.execute_step({"action": "custom_action"})

    assert result["ok"] is False
    assert result["error"] == "Unsupported action signature: custom_action"


def test_worker_returns_execution_failed_when_tool_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def exploding_tool(path: str) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_module, "TOOL_REGISTRY", {"read_file": exploding_tool})
    worker = Worker()

    result = worker.execute_step({"action": "read_file", "path": "file.txt"})

    assert result["ok"] is False
    assert "Worker execution failed for read_file: boom" == result["error"]

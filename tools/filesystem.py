from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from typing import Any

from tools.security import PROJECT_ROOT, ensure_not_project_root, is_command_safe, safe_path


MAX_OUTPUT_CHARS = 4000


def _trim_text(value: str) -> str:
    if len(value) <= MAX_OUTPUT_CHARS:
        return value
    return value[-MAX_OUTPUT_CHARS:]


def write_file(path: str, content: str) -> dict[str, Any]:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return {"ok": True, "path": str(file_path), "message": "File written successfully."}
    except Exception as exc:
        return {"ok": False, "error": f"write_file failed: {exc}"}


def apply_patch(path: str, patches: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        file_path = safe_path(path)
        if not file_path.exists():
            return {"ok": False, "error": f"File does not exist: {path}"}
        content = file_path.read_text(encoding="utf-8")
        original_content = content

        if not isinstance(patches, list) or not patches:
            return {"ok": False, "error": "apply_patch requires a non-empty patches list."}

        for index, patch in enumerate(patches, start=1):
            if not isinstance(patch, dict):
                return {"ok": False, "error": f"Patch #{index} must be an object."}
            old_text = str(patch.get("old_text", ""))
            new_text = str(patch.get("new_text", ""))
            if not old_text:
                return {"ok": False, "error": f"Patch #{index} is missing old_text."}

            occurrences = content.count(old_text)
            if occurrences == 0:
                return {"ok": False, "error": f"Patch #{index} old_text was not found in {path}."}
            if occurrences > 1:
                return {
                    "ok": False,
                    "error": (
                        f"Patch #{index} is ambiguous in {path}: old_text matched {occurrences} times. "
                        "Provide a larger unique block."
                    ),
                }

            content = content.replace(old_text, new_text, 1)

        file_path.write_text(content, encoding="utf-8")
        return {
            "ok": True,
            "path": str(file_path),
            "message": "Patch applied successfully." if content != original_content else "Patch made no changes.",
            "_display_content": content,
        }
    except Exception as exc:
        return {"ok": False, "error": f"apply_patch failed: {exc}"}


def append_file(path: str, content: str) -> dict[str, Any]:
    try:
        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as file:
            file.write(content)
        return {"ok": True, "message": "Content appended."}
    except Exception as exc:
        return {"ok": False, "error": f"append_file failed: {exc}"}


def read_file(path: str) -> dict[str, Any]:
    try:
        file_path = safe_path(path)
        if not file_path.exists():
            return {"ok": False, "error": f"File does not exist: {path}"}
        content = file_path.read_text(encoding="utf-8")
        return {"ok": True, "path": str(file_path), "content": _trim_text(content)}
    except Exception as exc:
        return {"ok": False, "error": f"read_file failed: {exc}"}


def run_command(command: str) -> dict[str, Any]:
    try:
        is_safe, reason = is_command_safe(command)
        if not is_safe:
            return {"ok": False, "error": reason}
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        prepared_command = command
        if platform.system() == "Windows":
            prepared_command = f"chcp 65001 > nul && {command}"
        completed = subprocess.run(
            prepared_command,
            shell=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            cwd=str(PROJECT_ROOT),
            env=env,
            timeout=60,
        )
        return {
            "ok": completed.returncode == 0,
            "command": command,
            "returncode": completed.returncode,
            "stdout": _trim_text(completed.stdout.strip()),
            "stderr": _trim_text(completed.stderr.strip()),
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Command timed out after 60 seconds"}
    except Exception as exc:
        return {"ok": False, "error": f"run_command failed: {exc}"}


def run_interactive_command(command: str) -> dict[str, Any]:
    try:
        is_safe, reason = is_command_safe(command)
        if not is_safe:
            return {"ok": False, "error": reason}
        process = subprocess.Popen(
            command,
            shell=True,
            stdin=sys.stdin,
            stdout=sys.stdout,
            stderr=sys.stderr,
            cwd=str(PROJECT_ROOT),
        )
        process.wait(timeout=60)
        return {
            "ok": process.returncode == 0,
            "command": command,
            "returncode": process.returncode,
            "message": "Command completed." if process.returncode == 0 else "Command exited with a non-zero status.",
        }
    except subprocess.TimeoutExpired:
        process.kill()
        return {"ok": False, "error": "Command timed out after 60 seconds"}
    except Exception as exc:
        return {"ok": False, "error": f"run_interactive_command failed: {exc}"}


def list_directory(path: str) -> dict[str, Any]:
    try:
        dir_path = safe_path(path)
        if not dir_path.exists():
            return {"ok": False, "error": f"Directory does not exist: {path}"}
        if not dir_path.is_dir():
            return {"ok": False, "error": f"Path is not a directory: {path}"}
        items = sorted([p.name for p in dir_path.iterdir()])
        return {"ok": True, "path": str(dir_path), "items": items}
    except Exception as exc:
        return {"ok": False, "error": f"list_directory failed: {exc}"}


def delete_directory(path: str) -> dict[str, Any]:
    try:
        dir_path = safe_path(path)
        ensure_not_project_root(dir_path)
        if not dir_path.exists():
            return {"ok": False, "error": f"Directory does not exist: {path}"}
        if not dir_path.is_dir():
            return {"ok": False, "error": f"Path is not a directory: {path}"}
        shutil.rmtree(dir_path)
        return {"ok": True, "path": str(dir_path), "message": "Directory deleted successfully."}
    except Exception as exc:
        return {"ok": False, "error": f"delete_directory failed: {exc}"}


def write_docx(path: str, content: str) -> dict[str, Any]:
    try:
        from docx import Document

        doc = Document()

        for line in content.split("\n"):
            if line.strip():
                doc.add_paragraph(line)

        file_path = safe_path(path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(file_path))
        return {"ok": True, "path": str(file_path), "message": "DOCX file created successfully."}
    except ImportError:
        return {"ok": False, "error": "python-docx is not installed, so write_docx is unavailable."}
    except Exception as exc:
        return {"ok": False, "error": f"write_docx failed: {exc}"}

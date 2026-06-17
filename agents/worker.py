from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import ValidationError

from schemas.models import WorkerStepInput
from tools.registry import TOOL_REGISTRY


class Worker:
    def __init__(self) -> None:
        self._cache: dict[str, dict[str, Any]] = {}

    def _cache_key(self, action: str, step: dict[str, Any]) -> str | None:
        if action == "read_file":
            return f"read_file:{step.get('path', '')}"
        if action == "list_directory":
            return f"list_directory:{step.get('path', '.')}"
        return None

    def _invalidate_file_cache(self, path: str) -> None:
        self._cache.pop(f"read_file:{path}", None)

        parent = Path(path).parent.as_posix() if path else "."
        if parent in {"", "."}:
            parent = "."
        self._cache.pop(f"list_directory:{parent}", None)

    def _invalidate_directory_cache(self, path: str) -> None:
        normalized = Path(path).as_posix() if path else "."
        if normalized in {"", "."}:
            normalized = "."

        parent = Path(normalized).parent.as_posix()
        if parent in {"", "."}:
            parent = "."

        self._cache.pop(f"list_directory:{normalized}", None)
        self._cache.pop(f"list_directory:{parent}", None)

        directory_prefixes = (
            f"read_file:{normalized}/",
            f"list_directory:{normalized}/",
        )
        keys_to_remove = [
            key for key in self._cache if key.startswith(directory_prefixes)
        ]
        for key in keys_to_remove:
            self._cache.pop(key, None)

    def _invalidate_cache_for_step(self, action: str, step: dict[str, Any]) -> None:
        path = str(step.get("path", "")).strip()
        if not path:
            return
        if action in {"write_file", "append_file", "apply_patch", "delete_file"}:
            self._invalidate_file_cache(path)
        elif action in {"delete_directory", "create_directory"}:
            self._invalidate_directory_cache(path)

    def execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        action = step.get("action")
        tool = TOOL_REGISTRY.get(action)
        if tool is None:
            return {"ok": False, "error": f"Unknown action: {action}"}

        try:
            validated_step = WorkerStepInput.model_validate(step)
            step_data = validated_step.model_dump()
            cache_key = self._cache_key(action, step_data) if isinstance(action, str) else None
            if cache_key is not None and cache_key in self._cache:
                return {**self._cache[cache_key], "_from_cache": True}

            if action in {"read_file", "list_directory", "delete_directory", "delete_file", "create_directory"}:
                result = tool(validated_step.path or ".")
            elif action in {"run_command", "run_interactive_command"}:
                result = tool(validated_step.command or "")
            elif action in {"write_file", "append_file", "write_docx"}:
                result = tool(validated_step.path or "", validated_step.content or "")
            elif action == "apply_patch":
                result = tool(
                    validated_step.path or "",
                    [patch.model_dump() for patch in validated_step.patches],
                )
            else:
                return {"ok": False, "error": f"Unsupported action signature: {action}"}

            if cache_key is not None and result.get("ok") is True:
                self._cache[cache_key] = dict(result)

            self._invalidate_cache_for_step(str(action), step_data)
            return result
        except ValidationError as exc:
            return {"ok": False, "error": f"Invalid step format: {exc}"}
        except Exception as exc:
            return {"ok": False, "error": f"Worker execution failed for {action}: {exc}"}

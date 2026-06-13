from __future__ import annotations

from typing import Any

from tools.registry import TOOL_REGISTRY


class Worker:
    def execute_step(self, step: dict[str, Any]) -> dict[str, Any]:
        action = step.get("action")
        tool = TOOL_REGISTRY.get(action)
        if tool is None:
            return {"ok": False, "error": f"Unknown action: {action}"}

        try:
            if action in {"read_file", "list_directory", "delete_directory"}:
                return tool(step.get("path", "."))
            if action in {"run_command", "run_interactive_command"}:
                return tool(step.get("command", ""))
            if action in {"write_file", "append_file", "write_docx"}:
                return tool(step.get("path", ""), step.get("content", ""))
            if action == "apply_patch":
                return tool(step.get("path", ""), step.get("patches", []))
            return {"ok": False, "error": f"Unsupported action signature: {action}"}
        except Exception as exc:
            return {"ok": False, "error": f"Worker execution failed for {action}: {exc}"}

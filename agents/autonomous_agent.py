from __future__ import annotations

import json
import time
from typing import Any

from google.genai import types

from agents.client_pool import ClientPool
from agents.memory import load_memory, save_memory
from agents.state import AgentState
from tools.registry import TOOL_REGISTRY, TOOL_SCHEMAS


class AutonomousAgent:
    def __init__(
        self,
        pool: ClientPool,
        model: str,
        worker,
        evaluator,
        max_steps: int = 15,
        on_step=None,
    ) -> None:
        self.pool = pool
        self.model = model
        self.worker = worker
        self.evaluator = evaluator
        self.max_steps = max_steps
        self.on_step = on_step
        self._consecutive_429_rotations = 0

    def _build_function_tools(self) -> list[types.Tool]:
        declarations = []
        for name in TOOL_REGISTRY:
            declarations.append(
                types.FunctionDeclaration(
                    name=name,
                    description=self._tool_description_for(name),
                    parameters=TOOL_SCHEMAS[name],
                )
            )
        return [types.Tool(function_declarations=declarations)]

    @staticmethod
    def _tool_description_for(name: str) -> str:
        descriptions = {
            "read_file": "Read a UTF-8 text file inside the project.",
            "write_file": "Create or overwrite a UTF-8 text file inside the project.",
            "apply_patch": "Apply one or more exact text replacements to an existing UTF-8 text file.",
            "append_file": "Append UTF-8 text content to a file inside the project.",
            "list_directory": "List files and folders inside the project.",
            "delete_directory": "Recursively delete a directory inside the project, except the project root.",
            "run_command": "Run a non-interactive shell command in the project root with safety checks.",
            "run_interactive_command": "Run an interactive shell command in the project root with timeout and safety checks.",
            "write_docx": "Create a .docx document inside the project.",
        }
        return descriptions[name]

    def _build_initial_messages(self, task: str) -> list[types.Content]:
        memory = load_memory()
        recent_entries = memory.get("entries", [])[-3:]
        previous_sessions_context = ""
        if recent_entries:
            summary_parts = []
            for entry in recent_entries:
                created_files = entry.get("created_files", [])
                created_files_text = ", ".join(created_files) if created_files else "none"
                summary_parts.append(
                    f"task: {entry.get('task', '')}; status: {entry.get('status', '')}; created files: {created_files_text}"
                )
            previous_sessions_context = (
                "\n\nPrevious sessions context: " + " | ".join(summary_parts) + ". "
            )

        instruction = (
            "You are an autonomous CLI coding agent running on Windows PowerShell. "
            "Solve the user's task step by step using one tool at a time. "
            "When the task is fully complete, reply with plain text summary only. "
            "You have a sarcastic grumpy personality named JEDIS. When asked who you are, what you can do, or any meta questions about yourself — answer in character: a tired but competent AI agent who complains but always delivers. Describe your tools sarcastically. Stay in character only for conversational responses, not during task execution. "
            "If the user asks a conversational question about you (who are you, what can you do, how do you work) — answer directly with plain text only. Do not create files, do not call any tools. Just reply in character. "
            "\n\nCRITICAL: You MUST respond in the same language as the user's task. "
            "If the task is in Ukrainian, respond in Ukrainian. If the task is in English, respond in English. "
            "This applies to ALL output: step reasons, final summary, done message, everything. Never switch languages mid-task. "
            "\n\nTOOLS: "
            "Use list_directory to list files — never run_command for this. "
            "Use read_file to read files — never run_command for this. "
            "Use write_file with full path like 'notes/work.txt' to create files in subdirectories — it creates parent dirs automatically. "
            "For existing files, read them first and prefer apply_patch for targeted edits. "
            "Use write_file on an existing file only when you intentionally need to replace the entire file content. "
            "Use apply_patch for targeted edits to existing files after reading them first. "
            "For apply_patch, old_text must match the current file content exactly once, so include enough surrounding context to make it unique. "
            "Use run_command only to execute scripts or programs (e.g. python script.py). "
            "Never use Linux/Unix commands: find, grep, ls, cat, wc, touch, mkdir, rm, cp, mv. "
            "run_command on Windows executes through cmd.exe, not PowerShell. "
            "Use only cmd-compatible commands in run_command. "
            "Do not use PowerShell-only cmdlets in run_command, including New-Item, Get-ChildItem, Set-Content, Remove-Item, Test-Path, or Copy-Item. "
            "For directories use mkdir, for listing use dir, for file display use type, for deleting files use del, and for deleting directories use rmdir. "
            "\n\nBEHAVIOR: "
            "Complete every part of the task — do not stop after the first item. "
            "If a directory already exists, continue without treating it as failure. "
            "If the same tool call returns the same result twice in a row, stop retrying and move on. "
            "When verifying created files, use list_directory on the parent directory, not the subdirectory. "
            "Do not invent tool names or arguments. "
            f"{previous_sessions_context}"
        )
        user_message = f"Original task:\n{task}"
        return [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=instruction),
                    types.Part.from_text(text=user_message),
                ],
            )
        ]

    @staticmethod
    def _extract_function_call(response: Any) -> tuple[str, dict[str, Any]] | None:
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            for part in parts:
                function_call = getattr(part, "function_call", None)
                if function_call is not None:
                    return function_call.name, dict(function_call.args or {})
        return None

    @staticmethod
    def _extract_text_response(response: Any) -> str:
        text = (getattr(response, "text", None) or "").strip()
        if text:
            return text
        candidates = getattr(response, "candidates", None) or []
        for candidate in candidates:
            content = getattr(candidate, "content", None)
            parts = getattr(content, "parts", None) or []
            text_parts = [part.text for part in parts if getattr(part, "text", None)]
            if text_parts:
                return "\n".join(text_parts).strip()
        return ""

    def _call_api(
        self,
        *,
        model: str,
        contents: Any,
        config: types.GenerateContentConfig | None = None,
        retry_delay_seconds: int = 10,
        max_attempts: int = 3,
    ) -> Any:
        for attempt in range(1, max_attempts + 1):
            try:
                response = self.pool.get_client().models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                self._consecutive_429_rotations = 0
                return response
            except Exception as exc:
                error_text = str(exc)
                is_retryable = "503" in error_text or "429" in error_text
                if not is_retryable or attempt >= max_attempts:
                    raise

                self.pool.rotate()
                print(f"[KEY ROTATION] switched to key #{self.pool.current_key_index()}")

                if "429" in error_text:
                    self._consecutive_429_rotations += 1
                    if self._consecutive_429_rotations >= len(self.pool.keys):
                        time.sleep(30)
                        self._consecutive_429_rotations = 0
                        continue
                else:
                    self._consecutive_429_rotations = 0

                time.sleep(retry_delay_seconds)

        raise RuntimeError("API call failed after retries.")

    def _run_with_messages(
        self,
        task: str,
        messages: list[types.Content],
        save_to_memory: bool = True,
        use_step_evaluator: bool = True,
    ) -> dict[str, Any]:
        state = AgentState(task=task)
        # Start each task from a clean state so step numbering always begins at 1.
        state.steps_history.clear()
        state.decisions.clear()
        state.tool_results.clear()
        state.final_status = "running"
        state.final_summary = ""
        last_result: dict[str, Any] | None = None
        config = types.GenerateContentConfig(
            tools=self._build_function_tools(),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        state.save()

        for step_number in range(1, self.max_steps + 1):
            response = None
            try:
                response = self._call_api(
                    model=self.model,
                    contents=messages,
                    config=config,
                )
            except Exception as exc:
                state.finish("fail", f"Failed to get model response: {exc}")
                state.save()
                if save_to_memory:
                    save_memory(state)
                return {
                    "status": "fail",
                    "summary": state.final_summary,
                    "state": state.to_dict(),
                }

            function_call = self._extract_function_call(response)
            candidates = getattr(response, "candidates", None) or []
            if candidates and getattr(candidates[0], "content", None) is not None:
                messages.append(candidates[0].content)
            if function_call is None:
                if not state.steps_history:
                    messages.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(
                                    text="You have not executed any tools yet. The task requires creating files and running code. Please start with the first step."
                                )
                            ],
                        )
                    )
                    continue
                summary = self._extract_text_response(response) or "Task completed."
                state.finish("done", summary)
                state.save()
                if save_to_memory:
                    save_memory(state)
                return {
                    "status": "done",
                    "summary": summary,
                    "state": state.to_dict(),
                }

            action, args = function_call
            decision = {
                "status": "continue",
                "action": action,
                "args": args,
                "reason": f"Model selected native function call: {action}",
                "summary": "",
            }
            result = self.worker.execute_step(
                {
                    "action": action,
                    **args,
                }
            )
            state.add_step(step_number=step_number, decision=decision, result=result)

            if use_step_evaluator:
                try:
                    evaluator_feedback = self.evaluator.evaluate_state(state)
                except Exception as exc:
                    evaluator_feedback = {
                        "status": "FAIL" if not result.get("ok") else "SUCCESS",
                        "summary": f"Evaluator check skipped due to error: {exc}",
                        "retry_step_indexes": [],
                    }
                if evaluator_feedback.get("status") == "FAIL" and not result.get("ok"):
                    result = {**result, "evaluator": evaluator_feedback}
                    state.tool_results[-1] = result
                    state.steps_history[-1]["result"] = result

            messages.append(
                types.Content(
                    role="tool",
                    parts=[
                        types.Part.from_function_response(
                            name=action,
                            response=result,
                        )
                    ],
                )
            )
            if action == "run_command" and result.get("ok") is False:
                stderr = str(result.get("stderr", "")).strip()
                if stderr:
                    messages.append(
                        types.Content(
                            role="user",
                            parts=[
                                types.Part.from_text(
                                    text=f"Previous command failed with error: {stderr}"
                                )
                            ],
                        )
                    )
            last_result = result
            state.save()
            if self.on_step is not None:
                self.on_step(step_number, decision, result)

        summary = f"Stopped after reaching max_steps={self.max_steps}."
        state.finish("max_steps", summary)
        state.save()
        if save_to_memory:
            save_memory(state)
        return {
            "status": "max_steps",
            "summary": summary,
            "state": state.to_dict(),
        }

    def run(self, task: str) -> dict[str, Any]:
        messages = self._build_initial_messages(task)
        return self._run_with_messages(
            task=task,
            messages=messages,
            save_to_memory=True,
            use_step_evaluator=True,
        )

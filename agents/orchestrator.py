from __future__ import annotations

import json
import re
import time
from typing import Any

from google.genai import types

from agents.autonomous_agent import AutonomousAgent
from agents.client_pool import ClientPool
from agents.memory import save_memory
from agents.state import AgentState
from tools.registry import TOOL_REGISTRY


class _CoderAgent(AutonomousAgent):
    def __init__(
        self,
        pool: ClientPool,
        model: str,
        worker,
        evaluator,
        subtask_context: str,
        max_steps: int = 15,
        on_step=None,
    ) -> None:
        super().__init__(
            pool=pool,
            model=model,
            worker=worker,
            evaluator=evaluator,
            max_steps=max_steps,
            on_step=on_step,
        )
        self.subtask_context = subtask_context

    def _build_initial_messages(self, task: str) -> list[types.Content]:
        instruction = (
            "You are the Coder sub-agent inside a multi-agent CLI coding pipeline running on Windows PowerShell. "
            "Execute the assigned subtask using exactly one tool call at a time and finish with a plain text summary only. "
            "Do not plan the whole project again. Focus only on the assigned subtask while preserving project consistency. "
            "All output must stay in the same language as the user's task. "
            "If the task is in Ukrainian, respond in Ukrainian. If the task is in English, respond in English. "
            "\n\nTOOLS: "
            "Use list_directory to inspect files and folders. "
            "Use read_file to inspect file contents. "
            "Use write_file with full relative paths when creating new files or intentionally replacing an entire file. "
            "For existing files, read them first and prefer apply_patch for targeted edits. "
            "Use apply_patch for targeted edits to existing files after reading them first. "
            "For apply_patch, old_text must match the current file content exactly once, so include enough surrounding context to make it unique. "
            "Use run_command only for running scripts or programs. "
            "Before writing tests, always use read_file to inspect the module under test and match class names, method names, function names, and file paths exactly as implemented. "
            "Never invent tool names or arguments. "
            "Never use Linux/Unix shell commands. "
            "run_command on Windows executes through cmd.exe, not PowerShell. "
            "Use only cmd-compatible commands in run_command. "
            "Do not use PowerShell-only cmdlets in run_command, including New-Item, Get-ChildItem, Set-Content, Remove-Item, Test-Path, or Copy-Item. "
            "For directories use mkdir, for listing use dir, for file display use type, for deleting files use del, and for deleting directories use rmdir. "
            "\n\nCONTEXT: "
            f"{self.subtask_context}"
        )
        user_message = f"Assigned subtask:\n{task}"
        return [
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=instruction),
                    types.Part.from_text(text=user_message),
                ],
            )
        ]

    def run(self, task: str) -> dict[str, Any]:
        messages = self._build_initial_messages(task)
        return self._run_with_messages(
            task=task,
            messages=messages,
            save_to_memory=False,
            use_step_evaluator=False,
        )


class OrchestratorAgent(AutonomousAgent):
    MAX_PLANNER_SUBTASKS = 15

    def __init__(
        self,
        pool: ClientPool,
        model: str,
        worker,
        evaluator,
        max_steps: int = 15,
        on_step=None,
        on_stage=None,
        planner_model: str | None = None,
        coder_model: str | None = None,
        subtask_delay_seconds: float = 0,
        max_subtask_retries: int = 1,
        max_review_cycles: int = 2,
    ) -> None:
        super().__init__(
            pool=pool,
            model=model,
            worker=worker,
            evaluator=evaluator,
            max_steps=max_steps,
            on_step=on_step,
        )
        self.on_stage = on_stage
        self.planner_model = planner_model or model
        self.coder_model = coder_model or model
        self.subtask_delay_seconds = max(0.0, subtask_delay_seconds)
        self.max_subtask_retries = max(0, max_subtask_retries)
        self.max_review_cycles = max(0, max_review_cycles)

    @staticmethod
    def _is_python_module_path(path: str) -> bool:
        normalized = path.replace("\\", "/").strip().lower()
        return normalized.endswith(".py") and not normalized.split("/")[-1].startswith("test_")

    @staticmethod
    def _is_test_subtask(subtask: str) -> bool:
        text = subtask.lower()
        return "test" in text or "pytest" in text or "unittest" in text

    @staticmethod
    def _extract_written_module_paths(result: dict[str, Any]) -> list[str]:
        state = result.get("state", {})
        steps_history = state.get("steps_history", [])
        module_paths: list[str] = []
        for step in steps_history:
            decision = step.get("decision", {})
            args = decision.get("args", {})
            action = decision.get("action")
            path = str(args.get("path", "")).strip()
            if action in {"write_file", "apply_patch"} and path and OrchestratorAgent._is_python_module_path(path):
                if path not in module_paths:
                    module_paths.append(path)
        return module_paths

    def _read_artifact_contents(self, paths: list[str]) -> list[dict[str, str]]:
        artifacts: list[dict[str, str]] = []
        for path in paths:
            result = self.worker.execute_step({"action": "read_file", "path": path})
            if result.get("ok"):
                artifacts.append(
                    {
                        "path": path,
                        "content": str(result.get("content", "")),
                    }
                )
        return artifacts

    @staticmethod
    def _select_relevant_artifacts(subtask: str, artifact_paths: list[str]) -> list[str]:
        if not artifact_paths:
            return []

        normalized_subtask = subtask.lower().replace("\\", "/")
        matches: list[str] = []
        for path in artifact_paths:
            normalized_path = path.lower().replace("\\", "/")
            filename = normalized_path.split("/")[-1]
            module_name = filename[:-3] if filename.endswith(".py") else filename
            if normalized_path in normalized_subtask or filename in normalized_subtask or module_name in normalized_subtask:
                matches.append(path)

        if matches:
            return matches

        if OrchestratorAgent._is_test_subtask(subtask):
            return artifact_paths
        return []

    @staticmethod
    def _format_artifact_context(artifacts: list[dict[str, str]]) -> str:
        if not artifacts:
            return ""
        parts = ["Relevant module artifacts:"]
        for artifact in artifacts:
            parts.append(f"Path: {artifact['path']}")
            parts.append("Content:")
            parts.append(artifact["content"])
        return "\n".join(parts)

    @staticmethod
    def _build_pipeline_state(task: str, status: str, summary: str, subtask_results: list[dict[str, Any]]) -> AgentState:
        state = AgentState(task=task)
        step_number = 0

        for subtask_result in subtask_results:
            subtask = str(subtask_result.get("subtask", "")).strip()
            subtask_state = subtask_result.get("state", {})
            steps_history = subtask_state.get("steps_history", [])

            for step in steps_history:
                step_number += 1
                decision = dict(step.get("decision", {}))
                result = dict(step.get("result", {}))
                if not decision.get("summary"):
                    decision["summary"] = subtask
                state.add_step(step_number=step_number, decision=decision, result=result)

        state.finish(status, summary)
        return state

    def _role_config(self) -> types.GenerateContentConfig:
        return types.GenerateContentConfig(
            tools=self._build_function_tools(),
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

    @staticmethod
    def _strip_json_block(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        object_start = cleaned.find("{")
        object_end = cleaned.rfind("}")
        if object_start != -1 and object_end != -1 and object_end >= object_start:
            return cleaned[object_start : object_end + 1]
        array_start = cleaned.find("[")
        array_end = cleaned.rfind("]")
        if array_start != -1 and array_end != -1 and array_end >= array_start:
            return cleaned[array_start : array_end + 1]
        raise ValueError("No JSON payload found.")

    @staticmethod
    def _escape_json_control_chars(text: str) -> str:
        result: list[str] = []
        in_string = False
        escaped = False

        for char in text:
            if escaped:
                result.append(char)
                escaped = False
                continue
            if char == "\\":
                result.append(char)
                escaped = True
                continue
            if char == '"':
                result.append(char)
                in_string = not in_string
                continue
            if in_string:
                code = ord(char)
                if char == "\n":
                    result.append("\\n")
                    continue
                if char == "\r":
                    result.append("\\r")
                    continue
                if char == "\t":
                    result.append("\\t")
                    continue
                if code < 32:
                    result.append(f"\\u{code:04x}")
                    continue
            result.append(char)

        return "".join(result)

    def _load_json_payload(self, raw_text: str) -> Any:
        payload = self._strip_json_block(raw_text)
        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            sanitized_payload = self._escape_json_control_chars(payload)
            return json.loads(sanitized_payload)

    @staticmethod
    def _extract_json_string_items(text: str) -> list[str]:
        items: list[str] = []
        decoder = json.JSONDecoder()
        index = 0

        while index < len(text):
            if text[index] != '"':
                index += 1
                continue
            try:
                item, end_index = decoder.raw_decode(text[index:])
            except json.JSONDecodeError:
                index += 1
                continue
            if isinstance(item, str):
                cleaned = item.strip()
                if cleaned:
                    items.append(cleaned)
            index += end_index

        return items

    @staticmethod
    def _normalize_planner_item(item: Any) -> str:
        if isinstance(item, str):
            return item.strip()
        if isinstance(item, dict):
            subtask = item.get("subtask")
            if isinstance(subtask, str):
                return subtask.strip()
        return str(item).strip()

    def _parse_planner_subtasks(self, raw_text: str) -> list[str]:
        try:
            data = self._load_json_payload(raw_text)
            if not isinstance(data, list):
                raise ValueError("Planner did not return a JSON array.")
            subtasks = [self._normalize_planner_item(item) for item in data]
            subtasks = [item for item in subtasks if item]
            if subtasks:
                return subtasks[: self.MAX_PLANNER_SUBTASKS]
        except Exception:
            pass

        string_items = self._extract_json_string_items(raw_text)
        if string_items:
            return string_items[: self.MAX_PLANNER_SUBTASKS]

        raise ValueError("Planner returned malformed JSON plan.")

    def _plan_subtasks(self, task: str) -> list[str]:
        prompt = f"""
You are the Planner sub-agent in a multi-agent coding pipeline.
Break the task into a concise ordered JSON array of actionable coding subtasks.
Return strict JSON only. No markdown. No explanations.

Rules:
- Return 1 to {self.MAX_PLANNER_SUBTASKS} items.
- Each item must be a short string.
- Keep subtasks concrete and implementation-focused.
- Each subtask must operate on a WHOLE FILE with full implementation, never split by individual methods or functions.
- Prefer fewer larger subtasks over many small ones. Aim for 4-6 subtasks maximum unless the task genuinely requires more.
- You MUST respond in the exact same language as the original task for every subtask string.
- If the original task is in Ukrainian, every subtask string MUST be in Ukrainian.
- If the original task is in English, every subtask string MUST be in English.
- Never switch languages or mix languages inside the plan.
- Respect the existing project structure and avoid changing unrelated behavior.
- Available tools are listed for context only; do not call tools in your response.

Available tools:
{", ".join(TOOL_REGISTRY.keys())}

Original task:
{task}
"""
        response = self._call_api(
            model=self.planner_model,
            contents=prompt,
            config=self._role_config(),
            retry_delay_seconds=15,
        )
        raw_text = self._extract_text_response(response)
        return self._parse_planner_subtasks(raw_text)

    def _review_results(
        self,
        task: str,
        plan: list[str],
        results: list[dict[str, Any]],
    ) -> dict[str, Any]:
        prompt = f"""
You are the Reviewer sub-agent in a multi-agent coding pipeline.
Review the original task, subtasks, and coder outputs.
Return strict JSON only with this schema:
{{
  "status": "SUCCESS" | "FAIL",
  "summary": "short overall summary",
  "issues": [
    {{
      "subtask": "which subtask has problem",
      "problem": "what exactly is wrong",
      "suggested_fix": "what should be done"
    }}
  ]
}}

Rules:
- Use SUCCESS only if the task appears complete.
- Use FAIL if any important requirement is missing or any subtask clearly failed.
- Keep the summary brief and concrete.
- Use an empty issues array when status is SUCCESS.
- You MUST write `summary`, `problem`, and `suggested_fix` in the exact same language as the original task.
- If the original task is in Ukrainian, `summary`, `problem`, and `suggested_fix` MUST all be in Ukrainian.
- If the original task is in English, `summary`, `problem`, and `suggested_fix` MUST all be in English.
- Never switch languages or mix languages inside the review output.
- Available tools are listed for context only; do not call tools in your response.

Available tools:
{", ".join(TOOL_REGISTRY.keys())}

Original task:
{task}

Plan:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Coder results:
{json.dumps(results, ensure_ascii=False, indent=2)}
"""
        response = self._call_api(
            model=self.planner_model,
            contents=prompt,
            config=self._role_config(),
        )
        raw_text = self._extract_text_response(response)
        data = self._load_json_payload(raw_text)
        if not isinstance(data, dict):
            raise ValueError("Reviewer returned non-object JSON payload.")
        status = str(data.get("status", "")).upper()
        if status not in {"SUCCESS", "FAIL"}:
            raise ValueError("Reviewer returned invalid status.")
        raw_issues = data.get("issues", [])
        if not isinstance(raw_issues, list):
            raise ValueError("Reviewer returned invalid issues.")
        issues = [item for item in raw_issues if isinstance(item, dict)]
        return {
            "status": status,
            "summary": str(data.get("summary", "")).strip(),
            "issues": issues,
        }

    def run(self, task: str) -> dict[str, Any]:
        try:
            plan = self._plan_subtasks(task)
            if self.on_stage is not None:
                self.on_stage("planner", {"status": "success", "plan": plan})
        except Exception as exc:
            if self.on_stage is not None:
                self.on_stage("planner", {"status": "fail", "error": str(exc)})
            return {
                "status": "fail",
                "summary": f"Planner failed: {exc}",
                "plan": [],
                "subtasks": [],
            }

        subtask_results: list[dict[str, Any]] = []
        module_artifact_paths: list[str] = []
        global_step = 0
        global_coder_runs = 0
        total_retries_used = 0
        review_cycle = 0

        for index, subtask in enumerate(plan, 1):
            if self.on_stage is not None:
                self.on_stage(
                    "coder_start",
                    {
                        "index": index,
                        "total": len(plan),
                        "subtask": subtask,
                    },
                )
            relevant_artifact_paths = self._select_relevant_artifacts(subtask, module_artifact_paths)
            relevant_artifacts = self._read_artifact_contents(relevant_artifact_paths)
            context = (
                f"Original task: {task}\n"
                f"Overall plan: {json.dumps(plan, ensure_ascii=False)}\n"
                f"Current subtask index: {index}\n"
                f"Completed subtask summaries: "
                f"{json.dumps([item.get('summary', '') for item in subtask_results], ensure_ascii=False)}"
            )
            artifact_context = self._format_artifact_context(relevant_artifacts)
            if artifact_context:
                context = f"{context}\n{artifact_context}"

            def on_subtask_step(step_number: int, decision: dict[str, Any], result: dict[str, Any]) -> None:
                nonlocal global_step
                global_step += 1
                if self.on_step is not None:
                    self.on_step(global_step, decision, result)

            attempt_context = context
            result: dict[str, Any] = {}
            for attempt in range(1, self.max_subtask_retries + 2):
                if attempt > 1:
                    if self.on_stage is not None:
                        self.on_stage(
                            "coder_retry",
                            {
                                "index": index,
                                "attempt": attempt,
                                "subtask": subtask,
                                "reason": result.get("summary", ""),
                            },
                        )
                    total_retries_used += 1

                global_coder_runs += 1
                coder = _CoderAgent(
                    pool=self.pool,
                    model=self.coder_model,
                    worker=self.worker,
                    evaluator=self.evaluator,
                    subtask_context=attempt_context,
                    max_steps=self.max_steps,
                    on_step=on_subtask_step,
                )
                result = coder.run(subtask)
                if result.get("status") == "done" or attempt > self.max_subtask_retries:
                    break

                retry_lines = [
                    attempt_context,
                    f"RETRY ATTEMPT {attempt}: Previous attempt failed.",
                    f"Failure summary: {result.get('summary', '')}",
                ]
                last_steps = result.get("state", {}).get("steps_history", [])[-2:]
                if last_steps:
                    retry_lines.append(f"Last actions: {json.dumps(last_steps, ensure_ascii=False)}")
                written_paths = self._extract_written_module_paths(result)
                if written_paths:
                    artifacts = self._read_artifact_contents(written_paths)
                    artifact_context = self._format_artifact_context(artifacts)
                    if artifact_context:
                        retry_lines.append(f"Files written in failed attempt: {artifact_context}")
                command_steps = result.get("state", {}).get("steps_history", [])
                last_command_output: dict[str, Any] | None = None
                for step in reversed(command_steps):
                    step_result = step.get("result", {})
                    stdout = str(step_result.get("stdout", "")).strip()
                    stderr = str(step_result.get("stderr", "")).strip()
                    if stdout or stderr:
                        last_command_output = {
                            "stdout": stdout,
                            "stderr": stderr,
                        }
                        break
                if last_command_output is not None:
                    retry_lines.append(
                        "Last command output: "
                        f"stdout={last_command_output['stdout']} "
                        f"stderr={last_command_output['stderr']}"
                    )
                attempt_context = "\n".join(retry_lines)

            if self.on_stage is not None:
                self.on_stage(
                    "coder_done",
                    {
                        "index": index,
                        "total": len(plan),
                        "subtask": subtask,
                        "status": result.get("status", "fail"),
                        "summary": result.get("summary", ""),
                    },
                )
            for module_path in self._extract_written_module_paths(result):
                if module_path not in module_artifact_paths:
                    module_artifact_paths.append(module_path)
            if self.subtask_delay_seconds > 0 and index < len(plan):
                time.sleep(self.subtask_delay_seconds)
            subtask_results.append(
                {
                    "subtask": subtask,
                    "status": result.get("status", "fail"),
                    "summary": result.get("summary", ""),
                    "state": result.get("state", {}),
                }
            )
            if result.get("status") != "done":
                pipeline_summary = f"Subtask failed: {subtask}. {result.get('summary', '')}".strip()
                pipeline_state = self._build_pipeline_state(task, "fail", pipeline_summary, subtask_results)
                save_memory(pipeline_state)
                return {
                    "status": "fail",
                    "summary": pipeline_summary,
                    "plan": plan,
                    "subtasks": subtask_results,
                }

        try:
            review = self._review_results(task, plan, subtask_results)
            if self.on_stage is not None:
                self.on_stage("reviewer", review)

            review_cycle = 1
            while review["status"] == "FAIL" and review_cycle < self.max_review_cycles:
                issues = review.get("issues", []) if isinstance(review, dict) else []
                filtered_issues = [item for item in issues if isinstance(item, dict)]
                if self.on_stage is not None:
                    self.on_stage(
                        "review_retry",
                        {
                            "cycle": review_cycle,
                            "issues_count": len(filtered_issues),
                        },
                    )
                repair_subtask = (
                    "Fix the following issues identified by the reviewer: "
                    f"{json.dumps(filtered_issues, ensure_ascii=False)}"
                )
                repair_context = (
                    f"REPAIR CYCLE {review_cycle}\n"
                    f"Original task: {task}\n"
                    f"Overall plan: {json.dumps(plan, ensure_ascii=False)}\n"
                    f"Previous subtask results: {json.dumps(subtask_results, ensure_ascii=False)}"
                )

                if self.on_stage is not None:
                    self.on_stage(
                        "repair_start",
                        {
                            "cycle": review_cycle,
                            "subtask": repair_subtask,
                        },
                    )

                def on_repair_step(step_number: int, decision: dict[str, Any], result: dict[str, Any]) -> None:
                    nonlocal global_step
                    global_step += 1
                    if self.on_step is not None:
                        self.on_step(global_step, decision, result)

                global_coder_runs += 1
                repair_coder = _CoderAgent(
                    pool=self.pool,
                    model=self.coder_model,
                    worker=self.worker,
                    evaluator=self.evaluator,
                    subtask_context=repair_context,
                    max_steps=self.max_steps,
                    on_step=on_repair_step,
                )
                repair_result = repair_coder.run(repair_subtask)
                for module_path in self._extract_written_module_paths(repair_result):
                    if module_path not in module_artifact_paths:
                        module_artifact_paths.append(module_path)
                subtask_results.append(
                    {
                        "subtask": repair_subtask,
                        "status": repair_result.get("status", "fail"),
                        "summary": repair_result.get("summary", ""),
                        "state": repair_result.get("state", {}),
                    }
                )

                if self.on_stage is not None:
                    self.on_stage(
                        "repair_done",
                        {
                            "cycle": review_cycle,
                            "summary": repair_result.get("summary"),
                        },
                    )

                review = self._review_results(task, plan, subtask_results)
                if self.on_stage is not None:
                    self.on_stage("reviewer", review)
                review_cycle += 1
        except Exception as exc:
            if self.on_stage is not None:
                self.on_stage("reviewer", {"status": "FAIL", "error": str(exc)})
            pipeline_summary = f"Reviewer failed: {exc}"
            pipeline_state = self._build_pipeline_state(task, "fail", pipeline_summary, subtask_results)
            save_memory(pipeline_state)
            return {
                "status": "fail",
                "summary": pipeline_summary,
                "plan": plan,
                "subtasks": subtask_results,
            }

        final_status = "done" if review["status"] == "SUCCESS" else "fail"
        final_summary = review["summary"] or "Multi-agent pipeline finished."
        pipeline_state = self._build_pipeline_state(task, final_status, final_summary, subtask_results)
        save_memory(pipeline_state)
        if self.on_stage is not None:
            self.on_stage(
                "pipeline_summary",
                {
                    "status": final_status,
                    "total_subtasks": len(plan),
                    "total_coder_runs": global_coder_runs,
                    "review_cycles": review_cycle,
                    "retries_used": total_retries_used,
                },
            )
        return {
            "status": final_status,
            "summary": final_summary,
            "plan": plan,
            "subtasks": subtask_results,
        }

from __future__ import annotations

import json
import re
from typing import Any, Callable

from google import genai
from pydantic import ValidationError

from agents.state import AgentState
from schemas.models import EvaluatorResponse


class Evaluator:
    def __init__(
        self,
        client: genai.Client | None = None,
        model: str = "gemini-2.5-flash",
        max_attempts: int = 3,
        client_getter: Callable[[], genai.Client] | None = None,
    ):
        if client is None and client_getter is None:
            raise ValueError("Evaluator requires either client or client_getter.")
        self._client_getter = client_getter or (lambda: client)
        self.model = model
        self.max_attempts = max_attempts

    def _get_client(self) -> genai.Client:
        client = self._client_getter()
        if client is None:
            raise ValueError("Evaluator client getter returned None.")
        return client

    @staticmethod
    def _strip_markdown_fence(text: str) -> str:
        cleaned = text.strip()
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise ValueError("No JSON object found.")
        return cleaned[start : end + 1]

    def evaluate(self, task: str, plan: list[dict[str, Any]], results: list[dict[str, Any]]) -> dict[str, Any]:
        prompt = f"""
You are an evaluator for a CLI agent.
Given:
1) Original user task
2) Executed steps
3) Execution results

Decide if task is complete.
Return strict JSON only with this schema:
{{
  "status": "SUCCESS" | "FAIL",
  "summary": "short summary",
  "retry_step_indexes": [0, 2]
}}

Rules:
- If complete, status must be SUCCESS and retry_step_indexes must be [].
- If not complete, status must be FAIL and retry_step_indexes should list indexes from provided steps.

Original task:
{task}

Plan:
{json.dumps(plan, ensure_ascii=False, indent=2)}

Results:
{json.dumps(results, ensure_ascii=False, indent=2)}
"""
        response = self._get_client().models.generate_content(
            model=self.model,
            contents=prompt,
        )
        raw_text = (response.text or "").strip()

        try:
            data = json.loads(self._strip_markdown_fence(raw_text))
            parsed = EvaluatorResponse.model_validate(data)
            return parsed.model_dump()
        except Exception:
            fallback_fail = [i for i, r in enumerate(results) if not r.get("ok")]
            if not fallback_fail:
                return {"status": "SUCCESS", "summary": "Completed based on tool results.", "retry_step_indexes": []}
            return {
                "status": "FAIL",
                "summary": "Could not parse evaluator output; retrying failed steps.",
                "retry_step_indexes": fallback_fail,
            }

    def evaluate_state(self, state: AgentState) -> dict[str, Any]:
        if not state.steps_history:
            return {"status": "SUCCESS", "summary": "No steps to evaluate yet.", "retry_step_indexes": []}

        prompt = f"""
You are an evaluator for an autonomous CLI agent.
Review the current state and decide whether the latest action appears acceptable.

Return strict JSON only:
{{
  "status": "SUCCESS" | "FAIL",
  "summary": "short summary",
  "retry_step_indexes": []
}}

Original task:
{state.task}

State history:
{json.dumps(state.steps_history, ensure_ascii=False, indent=2)}
"""
        response = self._get_client().models.generate_content(
            model=self.model,
            contents=prompt,
        )
        raw_text = (response.text or "").strip()
        try:
            data = json.loads(self._strip_markdown_fence(raw_text))
            parsed = EvaluatorResponse.model_validate(data)
            return parsed.model_dump()
        except Exception:
            latest_result = state.steps_history[-1]["result"]
            if latest_result.get("ok"):
                return {"status": "SUCCESS", "summary": "Latest step looks fine.", "retry_step_indexes": []}
            return {"status": "FAIL", "summary": "Latest step failed.", "retry_step_indexes": [len(state.steps_history) - 1]}

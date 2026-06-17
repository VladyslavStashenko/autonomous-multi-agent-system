from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class PatchOperation(BaseModel):
    old_text: str
    new_text: str


class WorkerStepInput(BaseModel):
    action: str
    path: str | None = None
    command: str | None = None
    content: str | None = None
    patches: list[PatchOperation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_by_action(self) -> "WorkerStepInput":
        if self.action in {"read_file", "list_directory", "delete_directory"} and not self.path:
            raise ValueError("path is required for this action")
        if self.action in {"run_command", "run_interactive_command"} and not self.command:
            raise ValueError("command is required for this action")
        if self.action in {"write_file", "append_file", "write_docx"}:
            if not self.path or self.content is None:
                raise ValueError("path and content are required for this action")
        if self.action == "apply_patch":
            if not self.path or not self.patches:
                raise ValueError("path and non-empty patches are required for apply_patch")
        return self


class EvaluatorResponse(BaseModel):
    status: Literal["SUCCESS", "FAIL"]
    summary: str = ""
    retry_step_indexes: list[int] = Field(default_factory=list)


class MemoryEntry(BaseModel):
    task: str
    status: str
    created_files: list[str] = Field(default_factory=list)
    ran_commands: list[str] = Field(default_factory=list)
    read_files: list[str] = Field(default_factory=list)
    timestamp: str

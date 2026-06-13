from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path.cwd().resolve()

_BLOCKED_PATTERNS = (
    "rm -rf",
    "del /s",
    "rmdir /s",
    "format",
    "shutdown",
    "powershell -enc",
    "curl | bash",
    "wget | bash",
    "sudo",
)


def safe_path(path: str) -> Path:
    raw_path = Path(path)
    candidate = (PROJECT_ROOT / raw_path).resolve() if not raw_path.is_absolute() else raw_path.resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError as exc:
        raise ValueError(f"Path escapes project root: {path}") from exc
    return candidate


def ensure_not_project_root(path: Path) -> None:
    if path == PROJECT_ROOT:
        raise ValueError("Refusing to operate on the project root.")


def is_command_safe(command: str) -> tuple[bool, str | None]:
    lowered = " ".join(command.lower().split())
    for pattern in _BLOCKED_PATTERNS:
        if pattern in lowered:
            return False, f"Blocked unsafe command pattern: {pattern}"
    return True, None

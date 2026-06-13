from __future__ import annotations

from google.genai import types

from tools.filesystem import (
    apply_patch,
    append_file,
    delete_directory,
    list_directory,
    read_file,
    run_command,
    run_interactive_command,
    write_docx,
    write_file,
)


TOOL_REGISTRY = {
    "write_file": write_file,
    "apply_patch": apply_patch,
    "append_file": append_file,
    "read_file": read_file,
    "run_command": run_command,
    "run_interactive_command": run_interactive_command,
    "list_directory": list_directory,
    "delete_directory": delete_directory,
    "write_docx": write_docx,
}

TOOL_SCHEMAS = {
    "read_file": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative path to a UTF-8 text file inside the project."),
        },
        required=["path"],
    ),
    "write_file": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative path to the file inside the project."),
            "content": types.Schema(type="STRING", description="Full UTF-8 text content to write."),
        },
        required=["path", "content"],
    ),
    "append_file": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative path to the file inside the project."),
            "content": types.Schema(type="STRING", description="Full UTF-8 text content to write."),
        },
        required=["path", "content"],
    ),
    "apply_patch": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative path to an existing text file inside the project."),
            "patches": types.Schema(
                type="ARRAY",
                items=types.Schema(
                    type="OBJECT",
                    properties={
                        "old_text": types.Schema(
                            type="STRING",
                            description="Exact existing text block to replace. It must match exactly once in the file.",
                        ),
                        "new_text": types.Schema(
                            type="STRING",
                            description="Replacement text block for the matched old_text.",
                        ),
                    },
                    required=["old_text", "new_text"],
                ),
                description="Ordered list of exact-match text replacements to apply to the file.",
            ),
        },
        required=["path", "patches"],
    ),
    "list_directory": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative directory path inside the project."),
        },
        required=["path"],
    ),
    "delete_directory": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative directory path inside the project to delete recursively."),
        },
        required=["path"],
    ),
    "run_command": types.Schema(
        type="OBJECT",
        properties={
            "command": types.Schema(type="STRING", description="A non-interactive shell command to run in the project root."),
        },
        required=["command"],
    ),
    "run_interactive_command": types.Schema(
        type="OBJECT",
        properties={
            "command": types.Schema(type="STRING", description="An interactive shell command to run in the project root."),
        },
        required=["command"],
    ),
    "write_docx": types.Schema(
        type="OBJECT",
        properties={
            "path": types.Schema(type="STRING", description="Relative .docx file path inside the project."),
            "content": types.Schema(type="STRING", description="Text content to place into the document."),
        },
        required=["path", "content"],
    ),
}


def get_available_tools_description() -> str:
    return "\n".join(
        [
            "- read_file(path): Read a UTF-8 text file inside the project.",
            "- write_file(path, content): Create or overwrite a UTF-8 text file inside the project.",
            "- apply_patch(path, patches): Apply one or more exact text replacements to an existing UTF-8 text file.",
            "- append_file(path, content): Append UTF-8 text content to a file inside the project.",
            "- list_directory(path): List files and folders inside the project.",
            "- delete_directory(path): Recursively delete a directory inside the project, except the project root.",
            "- run_command(command): Run a non-interactive shell command in the project root with safety checks.",
            "- run_interactive_command(command): Run an interactive shell command in the project root with timeout and safety checks.",
            "- write_docx(path, content): Create a .docx document inside the project.",
        ]
    )

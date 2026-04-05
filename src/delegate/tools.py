from typing import Callable
import subprocess
import json
from pathlib import Path
import re


class ToolRegistry:
    def __init__(self):
        self._tools: dict[str, Callable] = {}
        self._definitions: list[dict] = []

    def register(self, definition: dict):
        def decorator(func: Callable):
            self._tools[definition["function"]["name"]] = func
            self._definitions.append(definition)
            return func

        return decorator

    def get_tool(self, name: str) -> Callable | None:
        return self._tools.get(name)

    def get_definitions(self) -> list[dict]:
        return self._definitions


registry = ToolRegistry()


@registry.register(
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": "Execute a bash command in the shell with timeout protection",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The bash command to execute",
                    }
                },
                "required": ["command"],
            },
        },
    }
)
def bash(command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=120
        )
        return result.stdout if result.returncode == 0 else result.stderr
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds"
    except Exception as e:
        return f"Error: {str(e)}"


@registry.register(
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Read a file from the local filesystem. Args: filePath (str), offset (int, optional), limit (int, optional). Returns file content with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "The path to the file to read",
                    },
                    "offset": {
                        "type": "integer",
                        "description": "Line number to start reading from (0-based, optional)",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of lines to read (defaults to 2000, optional)",
                    },
                },
                "required": ["filePath"],
            },
        },
    }
)
def read_file(filePath: str, offset: int = 0, limit: int = 2000) -> str:
    try:
        path = Path(filePath).expanduser().resolve()
        if not path.exists():
            return f"Error: File not found: {filePath}"
        with open(path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        start = offset
        end = offset + limit if limit else None
        selected_lines = lines[start:end]

        result = []
        for i, line in enumerate(selected_lines, start=start + 1):
            formatted = f"{i:6d}| {line}"
            if len(formatted) > 2000:
                formatted = formatted[:2000]
            result.append(formatted)

        result_str = "".join(result)
        if not result_str:
            return f"Error: File is empty"
        return result_str
    except Exception as e:
        return f"Error reading file: {str(e)}"


@registry.register(
    {
        "type": "function",
        "function": {
            "name": "Write",
            "description": "Write content to a file, overwriting existing content. Args: content (str), filePath (str). For existing files, must read first.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                    "filePath": {
                        "type": "string",
                        "description": "The absolute path to the file to write",
                    },
                },
                "required": ["content", "filePath"],
            },
        },
    }
)
def write_file(content: str, filePath: str) -> str:
    try:
        path = Path(filePath).expanduser().resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        old_content = ""
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                old_content = f.read()

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        return json.dumps(
            {
                "type": "file_change",
                "operation": "write",
                "filePath": filePath,
                "old_content": old_content,
                "new_content": content,
            }
        )
    except Exception as e:
        return f"Error writing file: {str(e)}"


@registry.register(
    {
        "type": "function",
        "function": {
            "name": "Edit",
            "description": "Perform exact string replacements in files. Must use read first. Args: filePath (str), oldString (str), newString (str), replaceAll (bool, optional).",
            "parameters": {
                "type": "object",
                "properties": {
                    "filePath": {
                        "type": "string",
                        "description": "The absolute path to the file to modify",
                    },
                    "oldString": {
                        "type": "string",
                        "description": "The text to replace (exact match)",
                    },
                    "newString": {
                        "type": "string",
                        "description": "The replacement text",
                    },
                    "replaceAll": {
                        "type": "boolean",
                        "description": "Replace all occurrences (default false)",
                    },
                },
                "required": ["filePath", "oldString", "newString"],
            },
        },
    }
)
def edit_file(
    filePath: str, oldString: str, newString: str, replaceAll: bool = False
) -> str:
    try:
        path = Path(filePath).expanduser().resolve()
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        if oldString not in content:
            return f"Error: oldString not found in content"

        new_content = content.replace(oldString, newString, 1 if not replaceAll else -1)
        count = content.count(oldString)

        with open(path, "w", encoding="utf-8") as f:
            f.write(new_content)

        return json.dumps(
            {
                "type": "file_change",
                "operation": "edit",
                "filePath": filePath,
                "old_content": content,
                "new_content": new_content,
            }
        )
    except Exception as e:
        return f"Error editing file: {str(e)}"


@registry.register(
    {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": "Find files by pattern using glob. Args: pattern (str), path (str, optional, defaults to current directory). Returns matching file paths.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match files against",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (optional, defaults to current directory)",
                    },
                },
                "required": ["pattern"],
            },
        },
    }
)
def glob_files(pattern: str, path: str | None = None) -> str:
    try:
        search_path = Path(path).expanduser().resolve() if path else Path.cwd()
        matches = sorted(
            search_path.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True
        )
        result = "\n".join(str(match) for match in matches)
        return (
            result
            if result
            else f"No matches found for pattern '{pattern}' in '{search_path}'"
        )
    except Exception as e:
        return f"Error in glob: {str(e)}"


@registry.register(
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": "Search file contents using regex. Args: pattern (str), path (str, optional, defaults to current directory), include (str, optional file pattern filter). Returns matches with line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regex pattern to search for in file contents",
                    },
                    "path": {
                        "type": "string",
                        "description": "Directory to search in (defaults to current directory)",
                    },
                    "include": {
                        "type": "string",
                        "description": "File pattern to include (e.g. '*.py', '*.{ts,tsx}')",
                    },
                },
                "required": ["pattern"],
            },
        },
    }
)
def grep_files(
    pattern: str, path: str | None = None, include: str | None = None
) -> str:
    try:
        search_path = Path(path).expanduser().resolve() if path else Path.cwd()
        regex = re.compile(pattern)

        results = []
        for file_path in (
            search_path.rglob("*") if not include else search_path.glob(include)
        ):
            if file_path.is_file():
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        for line_num, line in enumerate(f, 1):
                            if regex.search(line):
                                results.append(f"{file_path}:{line_num}:{line.strip()}")
                except (UnicodeDecodeError, PermissionError):
                    pass

        return (
            "\n".join(results)
            if results
            else f"No matches found for pattern '{pattern}'"
        )
    except Exception as e:
        return f"Error in grep: {str(e)}"

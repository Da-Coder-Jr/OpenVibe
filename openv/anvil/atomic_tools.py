from __future__ import annotations

import difflib
import hashlib
import os
import subprocess
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolResult:
    ok: bool
    message: str
    data: dict[str, Any]


class BaseTool:
    name: str = "base"
    description: str = ""
    parameters: dict[str, Any] = {"type": "object", "properties": {}, "required": []}

    async def run(self, **kwargs: Any) -> ToolResult:
        raise NotImplementedError

    def spec(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class AtomicFileHandler:
    @staticmethod
    def read_with_checksum(path: Path) -> tuple[str, str]:
        if not path.exists():
            return "", AtomicFileHandler._checksum("")
        content = path.read_text(encoding="utf-8")
        return content, AtomicFileHandler._checksum(content)

    @staticmethod
    def _checksum(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    @staticmethod
    def write_if_clear(path: Path, new_content: str, original_checksum: str) -> tuple[bool, str]:
        current_content, current_checksum = AtomicFileHandler.read_with_checksum(path)
        if original_checksum and current_checksum != original_checksum:
            return False, "File changed since read; refusing to overwrite to prevent conflicts"
        if current_content == new_content:
            return True, "No changes required"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content, encoding="utf-8")
        return True, "File written safely"


class SmartWriteTool(BaseTool):
    name = "smart_write"
    description = "Safely write content to a file with checksum and diff awareness"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Target file path"},
            "content": {"type": "string", "description": "Desired file content"},
            "checksum": {"type": "string", "description": "Expected checksum to prevent overwriting"},
        },
        "required": ["path", "content"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path")
        new_content = kwargs.get("content")
        expected_checksum = kwargs.get("checksum")
        if not isinstance(path_str, str) or not isinstance(new_content, str):
            return ToolResult(False, "path and content are required", {})

        target = Path(path_str).expanduser().resolve()
        current_content, current_checksum = AtomicFileHandler.read_with_checksum(target)
        checksum_to_use = expected_checksum if isinstance(expected_checksum, str) else current_checksum

        diff = "\n".join(
            difflib.unified_diff(
                current_content.splitlines(),
                new_content.splitlines(),
                fromfile=str(target),
                tofile=f"{target} (new)",
                lineterm="",
            )
        )

        ok, message = AtomicFileHandler.write_if_clear(target, new_content, checksum_to_use)
        return ToolResult(ok, message, {"path": str(target), "checksum": current_checksum, "diff": diff})


class ListFilesTool(BaseTool):
    name = "list_files"
    description = "List files in a directory"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory to list (defaults to .)"},
        },
        "required": [],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path", ".")
        target = Path(path_str).expanduser().resolve()
        if not target.exists():
            return ToolResult(False, f"Directory {path_str} does not exist", {})

        try:
            files = [str(p.relative_to(target)) for p in target.rglob("*") if p.is_file()]
            if len(files) > 200:
                files = files[:200] + ["... (truncated)"]
            return ToolResult(True, f"Listed {len(files)} files", {"files": files})
        except Exception as e:
            return ToolResult(False, str(e), {})


class ReadFileTool(BaseTool):
    name = "read_file"
    description = "Read the content of a file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File to read"},
        },
        "required": ["path"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        path_str = kwargs.get("path")
        if not path_str:
            return ToolResult(False, "path is required", {})
        target = Path(path_str).expanduser().resolve()
        if not target.exists():
            return ToolResult(False, f"File {path_str} does not exist", {})

        try:
            content, checksum = AtomicFileHandler.read_with_checksum(target)
            return ToolResult(True, "File read successfully", {"content": content, "checksum": checksum})
        except Exception as e:
            return ToolResult(False, str(e), {})


class ShellExecuteTool(BaseTool):
    name = "shell_execute"
    description = "Execute a shell command"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to run"},
        },
        "required": ["command"],
    }

    async def run(self, **kwargs: Any) -> ToolResult:
        command = kwargs.get("command")
        if not command:
            return ToolResult(False, "command is required", {})

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return ToolResult(
                result.returncode == 0,
                f"Command exited with code {result.returncode}",
                {"stdout": result.stdout, "stderr": result.stderr, "code": result.returncode}
            )
        except subprocess.TimeoutExpired:
            return ToolResult(False, "Command timed out", {})
        except Exception as e:
            return ToolResult(False, str(e), {})


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        self._tools[tool.name] = tool

    def specs(self) -> list[dict[str, Any]]:
        return [tool.spec() for tool in self._tools.values()]

    async def execute(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(False, f"Unknown tool: {name}", {})
        return await tool.run(**arguments)

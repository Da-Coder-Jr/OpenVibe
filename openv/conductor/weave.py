from __future__ import annotations

import asyncio
import json
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from openv.anvil.atomic_tools import SmartWriteTool, ListFilesTool, ReadFileTool, ShellExecuteTool, ToolRegistry
from openv.loom.client import LoomClient, LoomError
from openv.scribe.telemetry import Scribe
from openv.vault.store import Vault


class WeaveConductor:
    def __init__(self, vault: Vault, loom: LoomClient, scribe: Scribe, model: str) -> None:
        self.vault = vault
        self.loom = loom
        self.scribe = scribe
        self.model = model
        self.console = Console()
        self.tools = ToolRegistry()
        self.tools.register(SmartWriteTool())
        self.tools.register(ListFilesTool())
        self.tools.register(ReadFileTool())
        self.tools.register(ShellExecuteTool())

    async def run_session(self, session_id: str) -> None:
        self.console.print(f"[bold cyan]OpenVibe[/] session: {session_id}")
        self.console.print("Type /exit to quit. Press Ctrl+C to interrupt streaming.")

        while True:
            try:
                user_input = self.console.input("[bold green]you> [/]").strip()
            except EOFError:
                break

            if user_input in {"/exit", "/quit"}:
                self.console.print("[yellow]Session closed.[/]")
                break
            if not user_input:
                continue

            self.vault.add_message(session_id, "user", user_input)
            try:
                await self._respond_cli(session_id)
            except KeyboardInterrupt:
                self.console.print("\n[red]Stream interrupted by user.[/]")
            except LoomError as exc:
                self.console.print(f"[red]{exc}[/]")
            except Exception as exc:
                self.console.print(f"[red]Unexpected conductor error: {exc}[/]")

    async def _respond_cli(self, session_id: str) -> None:
        """Helper for CLI-specific streaming output."""
        response_text = ""
        panel = Panel(Markdown(""), title="assistant", border_style="blue")

        with Live(panel, refresh_per_second=10, console=self.console) as live:
            async for event in self.ask_stream(session_id):
                if event["type"] == "token":
                    response_text += event["content"]
                    live.update(Panel(Markdown(response_text), title="assistant", border_style="blue"))
                elif event["type"] == "tool_start":
                    self.console.print(f"[magenta]tool[{event['name']}] starting...[/]")
                elif event["type"] == "tool_end":
                    self.console.print(f"[magenta]tool[{event['name']}] -> {event['result'].message}[/]")
                elif event["type"] == "error":
                    self.console.print(f"[red]{event['message']}[/]")
                elif event["type"] == "done":
                    usage = event["usage"]
                    self.console.print(
                        f"\n[dim]tokens prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}[/]"
                    )

    async def ask_stream(self, session_id: str):
        """
        The core logic of a single assistant turn (including tool calls).
        Yields events for the caller to handle (UI or CLI).
        """
        while True:
            history = self.vault.get_messages(session_id, limit=40)
            messages = [m.to_ollama_dict() for m in history]

            response_text = ""
            tool_calls = []

            async for chunk in self.loom.chat_stream(self.model, messages, self.tools.specs()):
                msg = chunk.get("message", {})

                piece = msg.get("content", "")
                if piece:
                    response_text += piece
                    yield {"type": "token", "content": piece}

                tcs = msg.get("tool_calls")
                if tcs:
                    for tc in tcs:
                        tool_calls.append(tc)

                if chunk.get("done"):
                    break

            self.vault.add_message(session_id, "assistant", response_text, tool_calls=tool_calls if tool_calls else None)

            if not tool_calls:
                usage = self.scribe.record_usage(json.dumps(messages), response_text, self.model)
                yield {"type": "done", "usage": usage}
                break

            for tc in tool_calls:
                tc_id = tc.get("id")
                func = tc.get("function", {})
                name = func.get("name", "")
                arguments = func.get("arguments", {})
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except json.JSONDecodeError:
                        arguments = {}

                yield {"type": "tool_start", "name": name, "arguments": arguments}
                result = await self.tools.execute(name, arguments)
                yield {"type": "tool_end", "name": name, "result": result}

                payload = json.dumps({"ok": result.ok, "message": result.message, "data": result.data})
                self.vault.add_message(session_id, "tool", payload, tool_call_id=tc_id)

from __future__ import annotations

import asyncio
import json
from typing import Any

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from openv.anvil.atomic_tools import SmartWriteTool, ToolRegistry
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

    async def run_session(self, session_id: str) -> None:
        self.console.print(f"[bold cyan]OpenV[/] session: {session_id}")
        self.console.print("Type /exit to quit. Press Ctrl+C to interrupt streaming.")

        while True:
            user_input = self.console.input("[bold green]you> [/]").strip()
            if user_input in {"/exit", "/quit"}:
                self.console.print("[yellow]Session closed.[/]")
                break
            if not user_input:
                continue

            self.vault.add_message(session_id, "user", user_input)
            try:
                await self._respond(session_id)
            except KeyboardInterrupt:
                self.console.print("\n[red]Stream interrupted by user.[/]")
            except LoomError as exc:
                self.console.print(f"[red]{exc}[/]")
            except Exception as exc:
                self.console.print(f"[red]Unexpected conductor error: {exc}[/]")

    async def _respond(self, session_id: str) -> None:
        history = self.vault.get_messages(session_id, limit=40)
        messages = [{"role": m.role, "content": m.content} for m in history]

        response_text = ""
        pending_tool_calls: list[dict[str, Any]] = []
        panel = Panel(Markdown(""), title="assistant", border_style="blue")

        with Live(panel, refresh_per_second=10, console=self.console) as live:
            async for chunk in self.loom.chat_stream(self.model, messages, self.tools.specs()):
                msg = chunk.get("message", {})
                piece = msg.get("content", "")
                if piece:
                    response_text += piece
                    live.update(Panel(Markdown(response_text), title="assistant", border_style="blue"))

                for tool_call in msg.get("tool_calls", []) or []:
                    pending_tool_calls.append(tool_call)

                if chunk.get("done"):
                    break

        if pending_tool_calls:
            tool_messages = await self._execute_tools(pending_tool_calls)
            for tool_message in tool_messages:
                self.vault.add_message(session_id, "tool", tool_message["content"])
            await self._respond(session_id)
            return

        usage = self.scribe.record_usage(json.dumps(messages), response_text, self.model)
        self.console.print(
            f"\n[dim]tokens prompt={usage.prompt_tokens} completion={usage.completion_tokens} total={usage.total_tokens}[/]"
        )
        self.vault.add_message(session_id, "assistant", response_text)

    async def _execute_tools(self, tool_calls: list[dict[str, Any]]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        for tool_call in tool_calls:
            func = tool_call.get("function", {})
            name = func.get("name", "")
            arguments_raw = func.get("arguments", "{}")
            try:
                arguments = json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
            except json.JSONDecodeError:
                arguments = {}
            result = await self.tools.execute(name, arguments)
            payload = json.dumps({"ok": result.ok, "message": result.message, "data": result.data})
            messages.append({"role": "tool", "content": payload})
            self.console.print(f"[magenta]tool[{name}] -> {result.message}[/]")
        return messages


def run_conductor(conductor: WeaveConductor, session_id: str) -> None:
    try:
        asyncio.run(conductor.run_session(session_id))
    except KeyboardInterrupt:
        conductor.console.print("\n[yellow]OpenV stopped.[/]")

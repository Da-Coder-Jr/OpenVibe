from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from openv.conductor.weave import WeaveConductor, run_conductor
from openv.default_config import DB_PATH, load_config
from openv.gui_app import OpenVGUI
from openv.loom.client import LoomClient
from openv.scribe.telemetry import Scribe
from openv.vault.store import Vault

app = typer.Typer(
    help="OpenVibe: Advanced Ollama-powered coding assistant",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()


def _build_runtime() -> tuple[dict, Vault, Scribe, LoomClient]:
    config = load_config()
    scribe = Scribe()
    vault = Vault(DB_PATH)
    loom = LoomClient(
        base_url=config["ollama"]["base_url"],
        timeout=int(config["ollama"]["timeout"]),
        scribe=scribe,
    )
    return config, vault, scribe, loom


@app.command(help="Start a new interactive coding session.")
def start(title: str = typer.Option("OpenVibe Session", "--title", "-t", help="Session title")) -> None:
    config, vault, scribe, loom = _build_runtime()
    session = vault.create_session(title)
    conductor = WeaveConductor(vault=vault, loom=loom, scribe=scribe, model=config["ollama"]["model"])

    console.print(Panel(f"Starting session: [bold cyan]{title}[/]\nID: [dim]{session.id}[/]", border_style="green"))
    run_conductor(conductor, session.id)


@app.command(help="Resume and chat in an existing session.")
def chat(session_id: str = typer.Argument(..., help="Existing session UUID or partial ID")) -> None:
    config, vault, scribe, loom = _build_runtime()

    # Try to find session by partial ID
    sessions = vault.list_sessions()
    target_id = None
    for s in sessions:
        if s.id.startswith(session_id):
            target_id = s.id
            break

    if not target_id:
        console.print(f"[red]No session found starting with '{session_id}'[/]")
        raise typer.Exit(code=1)

    try:
        session, _ = vault.resume_session(target_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1)

    conductor = WeaveConductor(vault=vault, loom=loom, scribe=scribe, model=config["ollama"]["model"])
    console.print(Panel(f"Resuming session: [bold cyan]{session.title}[/]", border_style="blue"))
    run_conductor(conductor, target_id)


@app.command(help="Check OpenVibe and Ollama health.")
def doctor() -> None:
    config, vault, _, loom = _build_runtime()
    table = Table(title="OpenVibe Health Check", box=None)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")

    db_ok = bool(vault.list_sessions() is not None)
    table.add_row("Vault DB", "[green]OK[/]" if db_ok else "[red]FAIL[/]")

    ollama_ok = asyncio.run(loom.check_health())
    table.add_row(
        f"Ollama ({config['ollama']['base_url']})",
        "[green]OK[/]" if ollama_ok else "[red]FAIL[/]",
    )

    console.print(table)
    if not ollama_ok:
        console.print("\n[yellow]Tip: Make sure Ollama is running and accessible.[/]")
        raise typer.Exit(code=1)


@app.command(name="list", help="List persisted sessions in Vault.")
def vault_list() -> None:
    _, vault, _, _ = _build_runtime()
    sessions = vault.list_sessions()

    if not sessions:
        console.print("[yellow]No sessions found in Vault.[/]")
        return

    table = Table(title="OpenVibe Sessions", header_style="bold magenta")
    table.add_column("ID (Short)", style="dim")
    table.add_column("Title", style="cyan")
    table.add_column("Last Updated", style="green")

    for row in sessions:
        table.add_row(row.id[:8], row.title, row.updated_at)

    console.print(table)


@app.command(help="Launch the OpenVibe desktop GUI.")
def ui() -> None:
    try:
        gui = OpenVGUI()
    except Exception as exc:
        console.print(f"[red]Unable to launch GUI: {exc}[/]")
        raise typer.Exit(code=1)
    gui.run()


if __name__ == "__main__":
    app()

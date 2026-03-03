from __future__ import annotations

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from openv.conductor.weave import WeaveConductor, run_conductor
from openv.default_config import DB_PATH, load_config
from openv.loom.client import LoomClient
from openv.scribe.telemetry import Scribe
from openv.vault.store import Vault

app = typer.Typer(help="OpenV terminal-native Ollama coding agent")
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


@app.command()
def start(title: str = typer.Option("OpenV Session", help="Session title")) -> None:
    """Start a new interactive session."""
    config, vault, scribe, loom = _build_runtime()
    session = vault.create_session(title)
    conductor = WeaveConductor(vault=vault, loom=loom, scribe=scribe, model=config["ollama"]["model"])
    run_conductor(conductor, session.id)


@app.command()
def chat(session_id: str = typer.Argument(..., help="Existing session UUID")) -> None:
    """Resume and chat in an existing session."""
    config, vault, scribe, loom = _build_runtime()
    try:
        vault.resume_session(session_id)
    except ValueError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(code=1)
    conductor = WeaveConductor(vault=vault, loom=loom, scribe=scribe, model=config["ollama"]["model"])
    run_conductor(conductor, session_id)


@app.command()
def doctor() -> None:
    """Check OpenV and Ollama health."""
    config, vault, _, loom = _build_runtime()
    table = Table(title="OpenV Doctor")
    table.add_column("Check")
    table.add_column("Status")

    db_ok = bool(vault.list_sessions() is not None)
    table.add_row("Vault DB", "OK" if db_ok else "FAIL")

    ollama_ok = asyncio.run(loom.check_health())
    table.add_row(
        f"Ollama @ {config['ollama']['base_url']}",
        "OK" if ollama_ok else "FAIL",
    )

    console.print(table)
    if not ollama_ok:
        raise typer.Exit(code=1)


@app.command(name="vault-list")
def vault_list() -> None:
    """List persisted sessions in Vault."""
    _, vault, _, _ = _build_runtime()
    sessions = vault.list_sessions()
    table = Table(title="Vault Sessions")
    table.add_column("Session ID")
    table.add_column("Title")
    table.add_column("Updated")

    for row in sessions:
        table.add_row(row.id, row.title, row.updated_at)

    console.print(table)


if __name__ == "__main__":
    app()

# OpenVibe

OpenVibe is an Ollama-powered coding assistant with both a terminal workflow and a desktop GUI mode.

## Features

- **CLI agent loop** with persisted sessions.
- **Vault session store** (SQLite) so conversations can be resumed.
- **Tool calling support** through the Weave conductor.
- **Desktop GUI** (`openv ui`) with:
  - sidebar session navigation,
  - one-click new sessions,
  - chat-style message view,
  - async assistant responses.

## Prerequisites

- Python **3.11+**
- A running Ollama-compatible endpoint:
  - local Ollama (`http://127.0.0.1:11434`), or
  - Ollama Cloud / hosted endpoint (set in config; see below).
- An installed/available model (default config uses `llama3.1`).

## Quick start

```bash
# 1) clone
git clone <your-fork-or-this-repo-url>
cd OpenVibe

# 2) create and activate a virtual environment
python -m venv .venv
source .venv/bin/activate

# 3) install runtime dependencies
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# 4) verify the CLI is available
python -m openv.cli.main --help
```

If step 4 fails with `ModuleNotFoundError: No module named "typer"`, your virtualenv is active but dependencies were not installed into it yet. Re-run step 3 in the same shell session.

## Configure Ollama

OpenVibe writes config to `~/.openv/config.json` on first run.

Default config:

```json
{
  "ollama": {
    "base_url": "http://127.0.0.1:11434",
    "model": "llama3.1",
    "timeout": 90
  },
  "ui": {
    "stream_panel_title": "OpenV • The Weave"
  }
}
```

If you want a different model or host, edit `~/.openv/config.json`.

### Using Ollama Cloud / hosted endpoints

OpenVibe only needs an Ollama-compatible `base_url`. If you are using a hosted endpoint, update `~/.openv/config.json`:

```json
{
  "ollama": {
    "base_url": "https://<your-endpoint>",
    "model": "<your-model>",
    "timeout": 90
  }
}
```

Then run:

```bash
python -m openv.cli.main doctor
```

If your hosted endpoint requires auth headers, you will need to run it through a local proxy that injects credentials (OpenVibe currently sends plain JSON requests without custom auth headers).


## CLI commands

Run commands with:

```bash
python -m openv.cli.main <command>
```

Available commands:

- `start` — create a fresh session and begin chatting.
- `chat <session_id>` — resume an existing session.
- `doctor` — verify local DB and Ollama health.
- `vault-list` — list stored sessions.
- `ui` — launch the OpenVibe Studio desktop app.

## Typical workflow

```bash
# Check local health (DB + Ollama reachability)
python -m openv.cli.main doctor

# Start a brand-new terminal session
python -m openv.cli.main start --title "My coding task"

# Later, list and resume
python -m openv.cli.main vault-list
python -m openv.cli.main chat <session_id>
```

## GUI mode

To launch the desktop app:

```bash
python -m openv.cli.main ui
```

The GUI stores sessions in the same vault DB (`~/.openv/vault.db`) as CLI mode.

## Data and logs

OpenVibe keeps all app data in `~/.openv/`:

- `config.json` — user configuration.
- `vault.db` — persisted sessions and messages.
- `logs/trace.json` — telemetry trace output.

## Troubleshooting

- **`doctor` reports Ollama FAIL**
  - Start Ollama and ensure it is listening on the configured `base_url`.
  - Pull the configured model (example): `ollama pull llama3.1`.
- **`ModuleNotFoundError` for `typer`, `rich`, or `httpx`**
  - Reinstall dependencies in your active environment:
    `python -m pip install -r requirements.txt`.
- **GUI does not open**
  - Ensure your environment supports Tkinter and desktop windows.

## Goal

This project is structured so OpenVibe can keep expanding toward an "OpenCode-like" experience: session history, better UX, and richer coding workflows in both terminal and GUI surfaces.

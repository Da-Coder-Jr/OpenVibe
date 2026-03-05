# OpenVibe

OpenVibe is a professional, Ollama-powered coding assistant with a modern desktop GUI and a powerful terminal workflow.

## Features

- **Modern Desktop GUI**: Built with CustomTkinter for a sleek, responsive, and cross-platform experience.
- **Advanced CLI Agent**: Persistent sessions with full tool calling support.
- **Smart Tooling**:
  - `smart_write`: Safely write files with checksum verification and diff awareness.
  - `read_file`: Access local source code.
  - `list_files`: Explore your project structure.
  - `shell_execute`: Run commands (tests, builds, etc.) directly.
- **Thinking Indicators**: Real-time feedback during AI processing and tool execution.
- **File Explorer Sidebar**: Integrated view of your project files in the GUI.
- **Vault Session Store**: All conversations are persisted in SQLite, allowing you to resume any session from CLI or GUI.
- **Streaming Responses**: Smooth, real-time token streaming for a more natural experience.

## Prerequisites

- **Python 3.11+**
- **Ollama**: A running Ollama instance (`http://127.0.0.1:11434` by default).
- **Model**: Default uses `llama3.1`, but you can configure any Ollama-compatible model.

## Quick start

```bash
# 1) Clone and enter
git clone <your-repo-url>
cd OpenVibe

# 2) Install dependencies
pip install -r requirements.txt

# 3) Launch OpenVibe GUI
python -m openv.cli.main ui
```

## CLI Usage

OpenVibe's CLI is perfect for terminal-native development:

```bash
# Start a new session
python -m openv.cli.main start --title "Refactor my logic"

# List all sessions
python -m openv.cli.main vault-list

# Resume a session
python -m openv.cli.main chat <session_id>

# Run a system check
python -m openv.cli.main doctor
```

## Configuration

OpenVibe automatically creates a config at `~/.openv/config.json`:

```json
{
  "ollama": {
    "base_url": "http://127.0.0.1:11434",
    "model": "llama3.1",
    "timeout": 90
  }
}
```

## Architecture

- `openv/conductor`: The "brain" managing the interaction loop (Weave Conductor).
- `openv/gui_app.py`: Modern UI implementation.
- `openv/anvil`: Tool implementations.
- `openv/vault`: SQLite-backed session and message storage.
- `openv/loom`: Ollama API client.
- `openv/scribe`: Telemetry and token usage estimation.

## Troubleshooting

- **Ollama FAIL**: Ensure Ollama is running and you've pulled the model: `ollama pull llama3.1`.
- **GUI Launch Error**: Ensure your environment supports Tkinter.
- **ModuleNotFoundError**: Re-run `pip install -r requirements.txt`.

OpenVibe is designed to be your local, private, and powerful coding companion.

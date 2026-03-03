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

## Commands

- `openv start` — create a fresh session and begin chatting.
- `openv chat <session_id>` — resume an existing session.
- `openv doctor` — verify local DB and Ollama health.
- `openv vault-list` — list stored sessions.
- `openv ui` — launch the OpenVibe Studio desktop app.

## Goal

This project is structured so OpenVibe can keep expanding toward an "OpenCode-like" experience: session history, better UX, and richer coding workflows in both terminal and GUI surfaces.

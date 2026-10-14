# Reiniery Agent Harness

A small AI agent harness built for UCLA EPSS 254. It uses an OpenAI-compatible
Chat Completions API, maintains conversation history, and gives the model one
tool: `bash`. Every proposed command requires explicit user approval.

## Features

- Local web chat served only on `127.0.0.1`
- One `bash` tool with a 60-second timeout and bounded output
- Approve or deny every command before it runs
- Per-call input, cached-input, and output token counts
- A 20-round tool limit for each user message
- Provider settings loaded from environment variables

## Install

Install [uv](https://docs.astral.sh/uv/), clone this repository, and run:

```bash
uv sync
cp .env.example .env
```

Edit `.env` and set `BASE_URL`, `API_KEY`, and a tool-capable `MODEL`. Never
commit `.env`.

## Run the web chat

```bash
uv run python web.py
```

Open <http://127.0.0.1:8000>. The server deliberately listens only on this
computer.

## Run the terminal chat

```bash
uv run python main.py
```

Type `/exit` to quit.

## How the loop works

The harness sends the complete message history and the `bash` tool schema to
the model. When the model returns a tool call, the harness asks for approval,
runs the command locally if approved, appends the output with the matching tool
call ID, and calls the model again. A normal text response ends the loop and
waits for the next user message.

## Status

The harness and local web interface are implemented and published. The complete
behavior checklist passes: single and multi-command tasks, command failure
recovery, denial handling, and growing per-call token counts. The installer
skill was validated from a fresh clone and submitted to the class repository.

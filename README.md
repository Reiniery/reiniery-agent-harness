# Reiniery Agent Harness

A small AI agent harness built for UCLA EPSS 254. It uses an OpenAI-compatible
Chat Completions API, maintains conversation history, and provides `bash` plus
tools loaded from local MCP plugins. Every proposed shell command requires
explicit user approval.

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

The harness sends conversation history and tool schemas to the model. The model
chooses a tool; the harness checks permissions, asks for approval when required,
executes the call, and appends its output with the matching tool-call ID. It then
calls the model again. A normal text response ends the turn.

## Status

The harness and local web interface are implemented and published. The complete
behavior checklist passes: single and multi-command tasks, command failure
recovery, denial handling, and growing per-call token counts. The installer
skill was validated from a fresh clone and submitted to the class repository.

## Plugins

Terminal chat (`uv run python main.py`) and web chat (`uv run python web.py`) now
load Claude-style plugins from `plugins/`. Each server stays connected for the session.
`reiniery-telegram` sends and receives private-chat messages; `reiniery-themis-density`
reads local 13-column THEMIS data for density summaries and sampling gaps.
Set Telegram credentials and THEMIS_DATA_DIR only in ignored `.env`.

The loader appends MCP tool schemas next to bash in each model request. It adds
skill names, descriptions and paths to the system prompt; full skill bodies remain
on disk until read through bash with approval. Environment variable values are
supplied to subprocesses, not automatically placed in model context. Never approve
a command that prints credentials. Startup lists plugins, tools and skills; request
usage reports the input token cost. The live connection test used 1,540 input tokens
on its first call (provider-specific usage, not a fixed plugin overhead).

`settings.toml` allowlists the two Telegram tools and three read-only research tools.
All other MCP tools require approval, and bash always requires approval even if
listed. Denial stops the rest of the turn. Review plugin code before trusting it.
Only one Telegram polling host should run at a time. Startup drops old messages;
only the configured private chat is accepted. Bot chats are not end-to-end encrypted.
Keep every shell approval enabled and revoke leaked tokens in BotFather.

## Telegram mode

Run `uv run python main.py --telegram`. For the current provider issue, use
`uv run python main.py --telegram --model openrouter/free` to select a free model
for this run. The saved model setting stays in `.env`. Keep the computer awake.

The harness owns polling; the model is not offered the receive tool. Each question
becomes a user turn, with history retained until `/new`. `/stop` stops the phone agent.
Bash and unlisted MCP tools require approval. Reply directly to the approval message
with `yes` or `no`, or send its displayed `yes CODE` / `no CODE`. A plain unthreaded
yes cannot approve anything. Approvals expire in five minutes; denial stops the turn.
Messages unrelated to an active approval are ignored until it finishes. Never approve
a command you do not understand or one that exposes secrets. Only your configured
private chat is accepted; startup skips messages sent while the agent was off.

## Week 3 status

Implementation and tests are complete. The student confirmed phone chat, command
approval, denial, and the multi-tool research question. Both plugins also worked
in Codex: inside/outside medians matched the source data and a test greeting was
sent. A real queued phone message was rejected with a wrong chat ID and skipped
by normal startup initialization. Sixteen automated regression tests pass.

Publication is pending student review. Both plugin folders and a submission README
are prepared under week-3/submissions/reiniery in the class repository. GitHub
sign-in works with network access. The saved NVIDIA model returned provider 404;
use --model openrouter/free for the validated phone run. Private data and credentials
remain local. See VALIDATION.md for evidence and scientific limitations.

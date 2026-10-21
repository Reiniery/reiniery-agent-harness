# Reiniery Telegram plugin

An MCP stdio server with `send_message(text)` and `wait_for_messages(seconds=30)`.
Requires Python 3.11+, uv, and environment variables `TELEGRAM_BOT_TOKEN` and
`TELEGRAM_CHAT_ID` (a positive private-chat ID). Put real values only in the
harness's ignored `.env`; the standalone server reads its environment.

From the harness root, load the environment locally, then start Claude Code:

```sh
set -a
. ./.env
set +a
claude --plugin-dir ./plugins/reiniery-telegram
```

For Codex, register this server using `codex mcp add` with `uv run --script`
and the absolute path to `server.py`, with both environment variables passed
from the local environment. Never paste credentials into chat or documentation.
Confirm current registration flags using `codex mcp add --help`.
The harness loads this plugin automatically in terminal and web chat. Run
`uv run python main.py --telegram` from the harness root for phone chat with command
approvals by reply. Add `--model openrouter/free` if the saved provider is unavailable.
The harness owns polling in this mode and hides the receive tool from the model.

Only the configured private chat is accepted. Other updates are dropped and
logged to stderr without their contents. Startup skips queued old updates.
Run just one polling process per bot; stop another host before starting the harness.
Long replies split into conservative 2,000-character chunks, including emoji.
Stdout carries MCP only; network errors do not expose token-bearing URLs.

Keep approval enabled for every shell command. A phone message alone does not
authorize a command. Telegram bot messages are not end-to-end encrypted; do not
send secrets. A leaked token must be revoked in BotFather using `/revoke`.

## Load in Codex from the harness repository

After `uv sync` and local `.env` configuration, run from the harness root:

```sh
codex mcp add reiniery-telegram -- "$PWD/.venv/bin/python" "$PWD/run_plugin.py" reiniery-telegram
```

The launcher reads only the plugin's required variables from local `.env` and
starts the same `server.py`. No credential values are stored in the Codex command.
Start a new Codex session and check `/mcp`. Stop the phone agent first so only one
Telegram poller runs. This plugin was tested in Codex via the same launcher and
ephemeral MCP configuration on October 20, 2026.

# THEMIS density plugin

Three read-only MCP tools describe coverage, summarize density over a UTC interval,
and find sampling gaps. Supports THA, THD, THE and inside/outside plasmapause summaries.
Requires Python 3.11+ and uv. No network API or credentials required.

Set THEMIS_DATA_DIR in the harness ignored .env to the absolute folder containing
`den-scpot-YYYYMMDD-tha-1.dat` files (also thd and the). Unset or blank uses the
bundled synthetic THA demonstration, which contains invented values, not observations.
Real research data are not bundled. The old THEMIS_DENSITY_CSV setting is unused.

Owner-confirmed whitespace columns: Unix time, year, month, day, hour, minute,
second, density (cm^-3), plasmapause flag (0 inside, 1 outside), L, MLT (hours),
MLAT (degrees), spacecraft number (1 THA, 4 THD, 5 THE).
The region flag is not a quality flag. No quality mask is inferred.

Query intervals include start and exclude end; use timezone-bearing ISO-8601,
e.g. 2008-06-01T00:00:00Z to 2008-06-02T00:00:00Z.
Column 1 is interpreted as Unix UTC; tools report disagreement with calendar columns
so the owner can review it. Statistics use finite positive densities and weight each
sample equally. Gap analysis uses all regions for one spacecraft and defaults to
300-second cadence × 1.5 tolerance. Gaps include query edges, may reflect dataset
selection, and are not evidence of instrument failure. Only the largest ten are listed.

Load .env locally, then use `claude --plugin-dir ./plugins/reiniery-themis-density`.
For Codex, register `uv run --script` with the absolute server.py path and
THEMIS_DATA_DIR in the server environment; consult `codex mcp add --help`.
The harness loads this plugin automatically in terminal and web chat. Never publish .env or private data.

## Load in Codex from the harness repository

After `uv sync` and local `.env` configuration, run from the harness root:

```sh
codex mcp add reiniery-themis-density -- "$PWD/.venv/bin/python" "$PWD/run_plugin.py" reiniery-themis-density
```

The launcher reads only the plugin's required variables from local `.env` and
starts the same `server.py`. No credential values are stored in the Codex command.
Start a new Codex session and check `/mcp`. Stop the phone agent first so only one
Telegram poller runs. This plugin was tested in Codex via the same launcher and
ephemeral MCP configuration on October 20, 2026.

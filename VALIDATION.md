# Week 3 validation — October 20, 2026

- Sixteen local regression tests pass: shell approval cannot be allowlisted away;
  denial cancels the rest of a tool batch; environment expansion; clear provider
  failures; web approval handling; Telegram reply correlation, nonce, timeout,
  invalid polling output, hidden receive tool, foreign-chat rejection, startup
  backlog acknowledgment, and emoji-safe message splitting.
- Live web chat loaded two plugins, five tools, two skill summaries, and sent the
  requested Telegram message. First-call input usage: 1,540 tokens on the test model.
- Student confirmed phone tests: file listing approved, disk-space request denied,
  and the research comparison answered. Logs show the skill read by approved bash
  and both research summaries returned. Denial made no subsequent tool call.
- Codex CLI 0.163.0-alpha.10.2 loaded the same two servers through run_plugin.py,
  called both research summaries, and sent the exact compatibility greeting once.
  No credential values were supplied in Codex configuration.
- Live wrong-chat test: the student's queued "security check" message was rejected
  and logged with a deliberately wrong configured ID. Normal startup initialization
  acknowledged and skipped the queued update; polling then returned no messages.
  The saved .env was unchanged and no commands ran during this check.

## Science and source boundaries

The real local data are not distributed. The plugin bundles only four invented
THA rows for reproducible demonstration. Owner-confirmed source columns are Unix
time, six UTC calendar fields, density cm^-3, region flag (0 inside / 1 outside
plasmapause), L, MLT, MLAT, and spacecraft number (1 THA / 4 THD / 5 THE).

THA June 1, 2008 UTC ([June 1, June 2)) has 189 rows: 50 inside (median 695.6 cm^-3)
and 139 outside (median 2.342 cm^-3). Peak is 12,420 cm^-3 at 08:00 UTC. These
results were checked independently against the file and reviewed by the student.
Earlier high-cadence CSV results used a different source and are not this plugin's
results. Its quality value 1283 is not interpreted as a plasmapause flag.

Queries use column 1 as Unix UTC and report disagreement with calendar columns.
Statistics are sample-weighted over finite positive densities. Region flags do not
establish quality. Gap spans can reflect dataset selection and do not prove
instrument downtime; defaults assume five-minute sampling and include query edges.

## Run

```sh
uv sync
uv run python -m unittest discover -s tests -v
uv run python main.py --telegram --model openrouter/free
```

The free route was used because the saved NVIDIA model returned provider 404.
API/provider availability is external; no fixed model availability is guaranteed.
Stop the phone harness before running another Telegram host. Secrets stay in ignored
.env and are not included in this evidence document or the submission.

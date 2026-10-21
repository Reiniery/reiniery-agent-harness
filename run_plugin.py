"""Launch a plugin with its required .env values, without storing secrets in host config."""
import argparse
import json
import os
from pathlib import Path

from dotenv import dotenv_values
from plugin_loader import Plugins


def main():
    root = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plugin", choices=[p.name for p in (root / "plugins").iterdir() if (p / ".mcp.json").is_file()])
    args = parser.parse_args()
    plugin = root / "plugins" / args.plugin
    servers = json.loads((plugin / ".mcp.json").read_text())["mcpServers"]
    if len(servers) != 1:
        raise SystemExit("This launcher expects one MCP server per plugin.")
    spec = next(iter(servers.values()))
    values = dotenv_values(root / ".env")
    for name in spec.get("env", {}):
        if name not in os.environ:
            os.environ[name] = values.get(name) or ""
    env = {**os.environ, **{k: Plugins.expand(v, plugin) for k, v in spec.get("env", {}).items()}}
    command = Plugins.expand(spec["command"], plugin)
    argv = [command] + [Plugins.expand(v, plugin) for v in spec.get("args", [])]
    os.execvpe(command, argv, env)


if __name__ == "__main__":
    main()

"""Discover plugins and keep their MCP clients alive on one background loop."""
import asyncio
import concurrent.futures
import json
import os
import re
import threading
import tomllib
from contextlib import AsyncExitStack
from pathlib import Path

import yaml
from mcp import Client, StdioServerParameters


class Plugins:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.tools = []
        self.skills = []
        self.names = []
        self.routes = {}
        self.allow = set()
        self.ready = concurrent.futures.Future()
        self.thread = None
        self.closed = False
        config = self.root / "settings.toml"
        if config.exists():
            self.allow = set(tomllib.loads(config.read_text()).get("permissions", {}).get("allow", []))

    @staticmethod
    def expand(text, plugin):
        def replace(match):
            name = match.group(1)
            if name == "CLAUDE_PLUGIN_ROOT":
                return str(plugin.resolve())
            if name not in os.environ:
                raise ValueError(f"Missing environment variable {name}; set it in .env.")
            return os.environ[name]
        return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace, text)

    async def serve(self):
        try:
            self.loop = asyncio.get_running_loop()
            self.queue = asyncio.Queue()
            async with AsyncExitStack() as stack:
                for plugin in sorted((self.root / "plugins").glob("*")):
                    manifest = plugin / ".claude-plugin/plugin.json"
                    if not manifest.is_file():
                        continue
                    self.names.append(json.loads(manifest.read_text())["name"])
                    for skill in sorted(plugin.glob("skills/*/SKILL.md")):
                        parts = skill.read_text().split("---", 2)
                        if len(parts) != 3 or parts[0].strip():
                            raise ValueError(f"Missing skill frontmatter: {skill}")
                        meta = yaml.safe_load(parts[1])
                        self.skills.append(f"{meta['name']}: {meta['description']} ({skill.resolve()})")
                    config = json.loads((plugin / ".mcp.json").read_text())
                    for server, spec in config["mcpServers"].items():
                        client = await stack.enter_async_context(Client(StdioServerParameters(
                            command=self.expand(spec["command"], plugin),
                            args=[self.expand(a, plugin) for a in spec.get("args", [])],
                            env={**os.environ, **{k: self.expand(v, plugin) for k, v in spec.get("env", {}).items()}},
                            cwd=plugin.resolve(),
                        )))
                        cursor = None
                        while True:
                            page = await client.list_tools(cursor=cursor)
                            for tool in page.tools:
                                name = f"{server}__{tool.name}"
                                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", name) or name in self.routes:
                                    raise ValueError("Invalid or duplicate MCP tool name.")
                                self.routes[name] = (client, tool.name)
                                self.tools.append({"type": "function", "function": {
                                    "name": name, "description": tool.description or "",
                                    "parameters": tool.input_schema,
                                }})
                            cursor = page.next_cursor
                            if cursor is None:
                                break
                self.ready.set_result(True)
                while True:
                    job = await self.queue.get()
                    if job is None:
                        break
                    name, arguments, future = job
                    try:
                        client, remote = self.routes[name]
                        result = await asyncio.wait_for(client.call_tool(remote, arguments), timeout=75)
                        text = "\n".join(b.text for b in result.content if b.type == "text")
                        future.set_result(("Tool error: " if result.is_error else "") + text)
                    except Exception:
                        # Transport exceptions can carry secret-bearing environment or URLs.
                        future.set_result("MCP tool failed. Check the server connection and configuration; do not retry a side effect without checking whether it completed.")
        except BaseException:
            if not self.ready.done():
                self.ready.set_exception(RuntimeError("Plugin startup failed. Check required .env variables and server configuration."))
            raise

    def __enter__(self):
        def runner():
            try:
                asyncio.run(self.serve())
            except BaseException:
                # Do not print nested SDK exceptions that may contain credentials.
                pass
        self.thread = threading.Thread(target=runner, name="mcp-plugins", daemon=True)
        self.thread.start()
        self.ready.result(timeout=120)
        print("Plugins:", ", ".join(self.names) or "none")
        print("MCP tools:", ", ".join(self.routes) or "none")
        print("Skills:", ", ".join(s.split(":", 1)[0] for s in self.skills) or "none")
        return self

    def call(self, name, arguments):
        if name not in self.routes:
            return f"Unknown tool: {name}"
        if self.closed or not self.thread.is_alive():
            return "MCP connection is closed. Restart the harness."
        future = concurrent.futures.Future()
        asyncio.run_coroutine_threadsafe(self.queue.put((name, arguments, future)), self.loop).result(timeout=5)
        return future.result(timeout=80)

    def needs_approval(self, name):
        return name == "bash" or name not in self.allow

    def skill_prompt(self):
        return "\n\nAvailable plugin skills (read the full SKILL.md with bash before using a skill):\n" + "\n".join(self.skills)

    def __exit__(self, *args):
        self.closed = True
        if self.thread and self.thread.is_alive():
            asyncio.run_coroutine_threadsafe(self.queue.put(None), self.loop).result(timeout=5)
            self.thread.join(timeout=85)

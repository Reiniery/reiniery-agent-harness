# /// script
# requires-python = ">=3.11"
# dependencies = ["mcp>=2,<3", "httpx>=0.28,<1"]
# ///
"""Private-chat Telegram transport. Stdout belongs exclusively to MCP."""
import asyncio
import json
import logging
import os
import re
import sys

import httpx
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


class Telegram:
    def __init__(self, token: str, chat_id: str):
        if not re.fullmatch(r"\d+:[A-Za-z0-9_-]+", token):
            raise ValueError("Set TELEGRAM_BOT_TOKEN to the BotFather token in .env.")
        if not re.fullmatch(r"[1-9]\d*", chat_id):
            raise ValueError("Set TELEGRAM_CHAT_ID to your positive private-chat ID in .env.")
        self.token = token
        self.chat_id = int(chat_id)
        self.offset = 0
        self.poll_lock = asyncio.Lock()

    async def request(self, method: str, **payload):
        try:
            async with httpx.AsyncClient(timeout=65) as client:
                response = await client.post(
                    f"https://api.telegram.org/bot{self.token}/{method}", json=payload
                )
                if response.status_code != 200:
                    raise RuntimeError(
                        f"Telegram HTTP {response.status_code}. Check credentials, network, "
                        "rate limits, and whether another bot process is polling."
                    )
                data = response.json()
        except (httpx.HTTPError, ValueError):
            # HTTP exceptions can contain the token-bearing request URL.
            raise RuntimeError("Telegram request failed. Check your connection and .env settings.") from None
        if not data.get("ok"):
            raise RuntimeError("Telegram rejected the request. Check bot settings and try again.")
        return data["result"]

    async def skip_backlog(self):
        updates = await self.request("getUpdates", offset=-1, timeout=0)
        if updates:
            self.offset = max(u["update_id"] for u in updates) + 1
            await self.request("getUpdates", offset=self.offset, timeout=0)

    async def send(self, text: str):
        if not text.strip():
            raise ValueError("Message is empty. Provide a short plain-text message.")
        # 2,000 code points stay below 4,096 UTF-16 units even for emoji.
        message_ids = []
        for start in range(0, len(text), 2000):
            message = await self.request("sendMessage", chat_id=self.chat_id, text=text[start:start+2000])
            message_ids.append(message["message_id"])
        return json.dumps({"sent": len(message_ids), "message_ids": message_ids})

    async def wait(self, seconds: int = 30):
        if not 0 <= seconds <= 50:
            raise ValueError("seconds must be between 0 and 50; try 30.")
        async with self.poll_lock:
            updates = await self.request("getUpdates", offset=self.offset, timeout=seconds)
            messages = []
            for update in updates:
                self.offset = max(self.offset, update["update_id"] + 1)
                message = update.get("message", {})
                chat = message.get("chat", {})
                if chat.get("id") != self.chat_id or chat.get("type") != "private":
                    print("Dropped update outside the authorized private chat.", file=sys.stderr)
                    continue
                if isinstance(message.get("text"), str):
                    messages.append({"message_id": message["message_id"], "text": message["text"],
                                     "date": message.get("date"),
                                     "reply_to_message_id": message.get("reply_to_message", {}).get("message_id")})
            return json.dumps(messages, ensure_ascii=False) if messages else "No new messages."


mcp = MCPServer("reiniery-telegram")
telegram: Telegram | None = None


@mcp.tool()
async def send_message(text: str) -> str:
    """Send plain text to the owner's fixed Telegram chat. Use for short replies or progress updates; never send secrets or whole files. Long text is split automatically. No recipient parameter is accepted."""
    if telegram is None:
        raise RuntimeError("Telegram is not initialized; restart the server with its environment variables.")
    try:
        return await telegram.send(text)
    except (ValueError, RuntimeError) as error:
        raise ToolError(str(error)) from None


@mcp.tool()
async def wait_for_messages(seconds: int = 30) -> str:
    """Wait 0–50 seconds (default 30) for new text from the owner's private chat. Return a JSON list of message IDs, text, dates and reply IDs, or 'No new messages.' Other chats are dropped. Only one process may poll this bot. In a Telegram harness, the harness owns this tool."""
    if telegram is None:
        raise RuntimeError("Telegram is not initialized; restart the server with its environment variables.")
    try:
        return await telegram.wait(seconds)
    except (ValueError, RuntimeError) as error:
        raise ToolError(str(error)) from None


if __name__ == "__main__":
    try:
        telegram = Telegram(os.getenv("TELEGRAM_BOT_TOKEN", ""), os.getenv("TELEGRAM_CHAT_ID", ""))
        asyncio.run(telegram.skip_backlog())
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
    mcp.run(transport="stdio")

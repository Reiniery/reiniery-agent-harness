import asyncio
import importlib.util
import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from telegram_mode import ChannelError, TelegramChat
from test_plugin_permissions import call, response


def chat_with_results(*results):
    plugins = Mock()
    plugins.routes = {"telegram__send_message": None, "telegram__wait_for_messages": None}
    plugins.call.side_effect = results
    return TelegramChat(plugins)


class Approval(unittest.TestCase):
    def test_old_yes_cannot_approve_new_request(self):
        chat = chat_with_results('{"message_ids":[100]}', json.dumps([
            {"text": "yes", "reply_to_message_id": 99},
            {"text": "yes"},
            {"text": "no", "reply_to_message_id": 100},
        ]))
        self.assertFalse(chat.approve("pwd"))

    def test_current_reply_approves(self):
        chat = chat_with_results('{"message_ids":[100]}', '[{"text":"yes","reply_to_message_id":100}]')
        self.assertTrue(chat.approve("pwd"))

    def test_uncertain_reply_declines(self):
        chat = chat_with_results('{"message_ids":[100]}', '[{"text":"maybe","reply_to_message_id":100}]')
        self.assertFalse(chat.approve("pwd"))

    def test_nonce_can_approve_without_reply(self):
        chat = chat_with_results('{"message_ids":[100]}', '[{"text":"yes abc123"}]')
        with patch("telegram_mode.secrets.token_hex", return_value="abc123"):
            self.assertTrue(chat.approve("pwd"))

    def test_timeout_does_not_approve(self):
        chat = chat_with_results('{"message_ids":[100]}', '{"message_ids":[101]}')
        chat.approval_timeout = 0
        self.assertFalse(chat.approve("pwd"))

    def test_poll_error_is_not_a_user_message(self):
        chat = chat_with_results("MCP tool failed")
        with self.assertRaises(ChannelError):
            chat.poll()

    def test_model_cannot_call_channel_polling_tool(self):
        client = Mock()
        client.chat.completions.create.side_effect = [response([call("telegram__wait_for_messages", {})]), response([])]
        plugins = Mock()
        plugins.tools = [{"type":"function","function":{"name":"telegram__wait_for_messages"}}]
        with patch.object(main, "show_usage"), patch.object(main, "execute_tool") as execute:
            main.run_agent_turn(client, "test", [], plugins, telegram_mode=True)
        execute.assert_not_called()
        offered = client.chat.completions.create.call_args_list[0].kwargs["tools"]
        self.assertEqual([t["function"]["name"] for t in offered], ["bash"])


class TelegramGateway(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        path = Path(__file__).resolve().parents[1] / "plugins/reiniery-telegram/server.py"
        spec = importlib.util.spec_from_file_location("telegram_gateway", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        self.bot = mod.Telegram("123:fake", "42")

    async def test_other_chat_dropped_and_offsets_advance(self):
        async def request(method, **payload):
            if payload["offset"]:
                return []
            return [
                {"update_id": 1, "message": {"chat":{"id":99,"type":"private"},"text":"bad","message_id":1}},
                {"update_id": 2, "message": {"chat":{"id":42,"type":"private"},"text":"good","message_id":2}},
            ]
        self.bot.request = request
        result = json.loads(await self.bot.wait(0))
        self.assertEqual([m["text"] for m in result], ["good"])
        self.assertEqual(await self.bot.wait(0), "No new messages.")
        self.assertEqual(self.bot.offset, 3)

    async def test_backlog_acknowledged_before_polling(self):
        calls = []
        async def request(method, **payload):
            calls.append(payload)
            return [{"update_id":100}] if payload["offset"] == -1 else []
        self.bot.request = request
        await self.bot.skip_backlog()
        self.assertEqual([c["offset"] for c in calls], [-1, 101])

    async def test_emoji_splitting_and_fixed_recipient(self):
        calls = []
        async def request(method, **payload):
            calls.append(payload)
            return {"message_id": len(calls)}
        self.bot.request = request
        result = json.loads(await self.bot.send("😀" * 4097))
        self.assertEqual(result["message_ids"], [1,2,3])
        self.assertTrue(all(c["chat_id"] == 42 and len(c["text"].encode("utf-16-le"))//2 <=4096 for c in calls))


if __name__ == "__main__":
    unittest.main()

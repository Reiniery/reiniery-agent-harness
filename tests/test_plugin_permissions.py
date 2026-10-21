import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
import httpx
from openai import NotFoundError

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import main
from plugin_loader import Plugins


def call(name, arguments, ident="one"):
    return SimpleNamespace(id=ident, function=SimpleNamespace(name=name, arguments=json.dumps(arguments)))


def response(calls):
    msg = SimpleNamespace(tool_calls=calls, content=None)
    msg.model_dump = lambda **kwargs: {"role": "assistant", "tool_calls": [
        {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}} for c in calls]}
    return SimpleNamespace(usage=None, choices=[SimpleNamespace(message=msg)])


class Permissions(unittest.TestCase):
    def test_bash_never_allowlisted(self):
        plugins = Plugins(Path(__file__).resolve().parents[1])
        plugins.allow.add("bash")
        self.assertTrue(plugins.needs_approval("bash"))
        self.assertTrue(plugins.needs_approval("unknown__tool"))

    def test_denial_stops_other_calls_and_model(self):
        client = Mock()
        client.chat.completions.create.return_value = response([
            call("bash", {"command": "pwd"}),
            call("telegram__send_message", {"text": "should not send"}, "two")])
        plugins = Mock(tools=[])
        plugins.needs_approval.side_effect = lambda name: name == "bash"
        with patch.object(main, "approve_command", return_value=False), patch.object(main, "show_usage"), patch.object(main, "execute_tool") as execute:
            messages = [{"role": "user", "content": "test"}]
            result = main.run_agent_turn(client, "test", messages, plugins)
        execute.assert_not_called()
        self.assertEqual(client.chat.completions.create.call_count, 1)
        self.assertEqual(len([m for m in messages if m["role"] == "tool"]), 2)
        self.assertIn("Declined", result)

    def test_environment_expansion(self):
        with patch.dict("os.environ", {"PLUGIN_TEST_VALUE": "test"}):
            self.assertEqual(Plugins.expand("${PLUGIN_TEST_VALUE}", Path(".")), "test")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing environment"):
                Plugins.expand("${NOT_DEFINED}", Path("."))

    def test_web_denial_stops_following_allowed_call(self):
        import web
        web.messages = []
        web.pending_calls = [call("bash", {"command": "pwd"}), call("telegram__send_message", {"text": "skip"}, "two")]
        with patch.object(web, "execute_tool") as execute:
            r = web.app.test_client().post("/api/decision", json={"approved": False})
        self.assertEqual(r.status_code, 200)
        execute.assert_not_called()
        self.assertFalse(web.pending_calls)

    def test_web_trusted_tool_then_approval(self):
        import web
        web.messages = []
        web.pending_calls = [call("telegram__send_message", {"text": "test"}), call("bash", {"command": "pwd"}, "two")]
        plugins = Mock()
        plugins.needs_approval.side_effect = lambda name: name == "bash"
        with patch.object(web, "plugins", plugins), patch.object(web, "execute_tool", return_value="sent") as execute:
            events = web.drain_pending()
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(events[-1]["type"], "approval")
        self.assertEqual(len(web.pending_calls), 1)
        web.pending_calls = []

    def test_provider_failure_returns_clear_message(self):
        import web
        error = NotFoundError("provider detail that should not be shown", response=httpx.Response(404, request=httpx.Request("POST", "https://example.invalid")), body=None)
        client = Mock()
        client.chat.completions.create.side_effect = error
        web.messages = []
        web.tool_rounds = 0
        with patch.object(web, "client", client):
            events = web.advance_agent()
        self.assertIn("HTTP 404", events[0]["content"])
        self.assertNotIn("provider detail", events[0]["content"])


if __name__ == "__main__":
    unittest.main()

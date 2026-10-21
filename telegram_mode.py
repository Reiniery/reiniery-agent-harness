"""The harness owns Telegram polling and correlates each approval to its request."""
import json
import secrets
import time


class ChannelError(RuntimeError):
    pass


class TelegramChat:
    def __init__(self, plugins, approval_timeout=300):
        self.plugins = plugins
        self.approval_timeout = approval_timeout
        self.stop_requested = False
        self.reset_requested = False
        required = {"telegram__send_message", "telegram__wait_for_messages"}
        if not required <= set(plugins.routes):
            raise ChannelError("Telegram plugin is missing its send or receive tool.")

    def send(self, text):
        result = self.plugins.call("telegram__send_message", {"text": text})
        try:
            data = json.loads(result)
            ids = data["message_ids"]
            if not ids or not all(isinstance(i, int) for i in ids):
                raise ValueError
            return ids
        except (ValueError, KeyError, TypeError):
            raise ChannelError("Could not confirm Telegram delivery. Check the bot connection.") from None

    def poll(self, seconds=30):
        result = self.plugins.call("telegram__wait_for_messages", {"seconds": seconds})
        if result == "No new messages.":
            return []
        try:
            messages = json.loads(result)
            if not isinstance(messages, list) or any(not isinstance(m, dict) or not isinstance(m.get("text"), str) for m in messages):
                raise ValueError
            return messages
        except (ValueError, TypeError):
            raise ChannelError("Telegram polling failed. Stop other polling hosts and check the connection.") from None

    def approve(self, command):
        code = secrets.token_hex(3)
        ids = set(self.send(
            f"Run this command/tool?\n\n{command}\n\n"
            f"Reply directly to this message with yes or no.\n"
            f"Or send: yes {code} / no {code}\n"
            "Approval expires in 5 minutes. Other messages during this approval are ignored."
        ))
        deadline = time.monotonic() + self.approval_timeout
        while time.monotonic() < deadline:
            messages = self.poll(min(30, max(1, int(deadline-time.monotonic()))))
            for message in messages:
                answer = message["text"].strip().lower()
                # Old or unrelated 'yes' messages cannot approve a later command.
                if message.get("reply_to_message_id") in ids:
                    return answer == "yes"
                if answer in {f"yes {code}", f"no {code}"}:
                    return answer == f"yes {code}"
                if answer in {"/stop", "/new"}:
                    self.stop_requested = answer == "/stop"
                    self.reset_requested = answer == "/new"
                    return False
        self.send("Approval expired. The command was not run.")
        return False

    def run(self, client, model, system_prompt):
        from main import run_agent_turn
        prompt = system_prompt + (
            "\nThe user is chatting through Telegram. Keep replies short and plain. "
            "The harness owns polling and sends final answers. Use send_message only for progress updates. "
            "Never send credentials or whole files. The harness asks for every shell approval. "
            "Use /new to reset conversation."
        )
        messages = [{"role": "system", "content": prompt}]
        self.send("Your agent is ready. Ask a research question or ask what files are in the harness folder. Commands require approval by reply. /new resets the conversation; /stop stops the agent.")
        print("Telegram chat ready. Waiting for your phone. Press Ctrl-C to stop.")
        try:
            while True:
                incoming = self.poll()
                for message in incoming:
                    text = message["text"].strip()
                    if text == "/stop":
                        self.send("Agent stopped. Restart it on your computer when needed.")
                        return
                    if text == "/new":
                        messages = [{"role": "system", "content": prompt}]
                        self.send("Started a fresh conversation.")
                        continue
                    if not text or message.get("reply_to_message_id") or text.lower().split()[0] in {"yes", "no"}:
                        self.send("No approval is pending. Send a new question to continue.")
                        continue
                    messages.append({"role": "user", "content": text})
                    self.send("Working on your question…")
                    answer = run_agent_turn(client, model, messages, self.plugins, approve=self.approve, telegram_mode=True)
                    self.send(answer or "The model returned no answer. Please try again.")
                    if self.stop_requested:
                        self.send("Agent stopped. Restart it on your computer when needed.")
                        return
                    if self.reset_requested:
                        messages = [{"role": "system", "content": prompt}]
                        self.reset_requested = False
                        self.send("Started a fresh conversation.")
        except KeyboardInterrupt:
            print("Telegram chat stopped.")

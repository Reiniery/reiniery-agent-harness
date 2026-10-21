import json
import os
import subprocess
import argparse
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI, APIError
from plugin_loader import Plugins


MAX_OUTPUT_CHARS = 10_000
COMMAND_TIMEOUT_SECONDS = 60
MAX_TOOL_ROUNDS = 20

BASH_TOOL = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": (
            "Run a Bash command in the harness working directory. "
            "Use it to inspect files, run programs, and complete tasks."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The Bash command to run.",
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}


def run_bash(command: str) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            executable="/bin/bash",
            cwd=Path.cwd(),
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
        )
        output = (
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}\n"
            f"exit_code: {result.returncode}"
        )
    except subprocess.TimeoutExpired as error:
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode(errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode(errors="replace")
        output = (
            f"stdout:\n{stdout}\n"
            f"stderr:\n{stderr}\n"
            f"error: command timed out after {COMMAND_TIMEOUT_SECONDS} seconds"
        )

    if len(output) > MAX_OUTPUT_CHARS:
        output = "[Earlier output truncated]\n" + output[-MAX_OUTPUT_CHARS:]
    return output


def approve_command(command: str) -> bool:
    print(f"\nProposed command:\n{command}")
    answer = input("Run this command? [y/N]: ").strip().lower()
    return answer in {"y", "yes"}


def show_usage(usage) -> None:
    if usage is None:
        print("Token usage unavailable from provider.")
        return
    details = usage.prompt_tokens_details
    cached = details.cached_tokens if details and details.cached_tokens is not None else 0
    print(
        f"Tokens: input={usage.prompt_tokens}, "
        f"cached={cached}, output={usage.completion_tokens}"
    )


def execute_tool(name, arguments, plugins=None):
    if name == "bash":
        command = arguments.get("command")
        if not isinstance(command, str):
            return "Invalid bash arguments: command must be a string."
        return run_bash(command)
    return plugins.call(name, arguments) if plugins else f"Unknown tool: {name}"


def run_agent_turn(client: OpenAI, model: str, messages: list[dict], plugins=None, approve=None, telegram_mode=False) -> str:
    tools = [BASH_TOOL] + (plugins.tools if plugins else [])
    if telegram_mode:
        tools = [tool for tool in tools if tool["function"]["name"] != "telegram__wait_for_messages"]
    available = {tool["function"]["name"] for tool in tools}
    approve = approve or approve_command
    for _ in range(MAX_TOOL_ROUNDS):
        try:
            response = client.chat.completions.create(model=model, messages=messages, tools=tools)
        except APIError as error:
            answer = f"Model request failed (HTTP {getattr(error, 'status_code', None) or 'connection error'}). Check MODEL and provider availability; retry when resolved."
            messages.append({"role": "assistant", "content": answer})
            return answer
        show_usage(response.usage)
        assistant_message = response.choices[0].message
        messages.append(assistant_message.model_dump(exclude_none=True))
        if not assistant_message.tool_calls:
            return assistant_message.content or ""
        declined = False
        for call in assistant_message.tool_calls:
            try:
                arguments = json.loads(call.function.arguments)
                if not isinstance(arguments, dict):
                    raise ValueError("arguments must be an object")
                name = call.function.name
                if name not in available:
                    raise ValueError("Tool is not available in this mode.")
                asks = plugins.needs_approval(name) if plugins else True
                prompt = arguments.get("command", "") if name == "bash" else f"{name}: {json.dumps(arguments)}"
                if declined or (asks and not approve(prompt)):
                    declined = True
                    result = "The user declined. This turn is stopped; do not attempt an alternative."
                else:
                    result = execute_tool(name, arguments, plugins)
            except (json.JSONDecodeError, ValueError, TypeError) as error:
                result = f"Invalid tool arguments: {error}"
            result = result[:MAX_OUTPUT_CHARS]
            print(f"Result:\n{result}\n")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})
        if declined:
            answer = "Declined. I stopped this turn without running further tools."
            messages.append({"role": "assistant", "content": answer})
            return answer
    answer = f"Stopped after {MAX_TOOL_ROUNDS} tool rounds."
    messages.append({"role": "assistant", "content": answer})
    return answer


def main() -> None:
    parser = argparse.ArgumentParser(description="Chat locally or from your private Telegram bot.")
    parser.add_argument("--telegram", action="store_true", help="Receive questions and command approvals through Telegram.")
    parser.add_argument("--model", help="Override MODEL for this run (e.g. openrouter/free).")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    load_dotenv(root / ".env")
    os.chdir(root)
    client = OpenAI(
        base_url=os.environ["BASE_URL"],
        api_key=os.environ["API_KEY"],
        timeout=60,
        max_retries=0,
    )
    model = args.model or os.environ["MODEL"]
    with Plugins(root) as plugins:
        system_prompt = Path("system_prompt.md").read_text().strip() + plugins.skill_prompt()
        if args.telegram:
            from telegram_mode import TelegramChat, ChannelError
            try:
                TelegramChat(plugins).run(client, model, system_prompt)
            except ChannelError as error:
                print(str(error))
            return
        messages = [{"role": "system", "content": system_prompt}]
        print("Chat started. Type /exit to quit.")
        while True:
            user_message = input("You: ").strip()
            if user_message == "/exit":
                break
            if not user_message:
                continue
            messages.append({"role": "user", "content": user_message})
            assistant_message = run_agent_turn(client, model, messages, plugins)
            print(f"Assistant: {assistant_message}")


if __name__ == "__main__":
    main()

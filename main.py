import os
import subprocess
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


MAX_OUTPUT_CHARS = 10_000
COMMAND_TIMEOUT_SECONDS = 60

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


def show_usage(usage) -> None:
    details = usage.prompt_tokens_details
    cached = details.cached_tokens if details and details.cached_tokens is not None else 0
    print(
        f"Tokens: input={usage.prompt_tokens}, "
        f"cached={cached}, output={usage.completion_tokens}"
    )


def main() -> None:
    load_dotenv()
    client = OpenAI(
        base_url=os.environ["BASE_URL"],
        api_key=os.environ["API_KEY"],
    )
    model = os.environ["MODEL"]
    system_prompt = Path("system_prompt.md").read_text().strip()
    messages = [{"role": "system", "content": system_prompt}]

    print("Chat started. Type /exit to quit.")
    while True:
        user_message = input("You: ").strip()
        if user_message == "/exit":
            break
        if not user_message:
            continue

        messages.append({"role": "user", "content": user_message})
        response = client.chat.completions.create(model=model, messages=messages)
        assistant_message = response.choices[0].message.content or ""
        messages.append({"role": "assistant", "content": assistant_message})

        print(f"Assistant: {assistant_message}")
        show_usage(response.usage)


if __name__ == "__main__":
    main()

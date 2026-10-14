import json
import os
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI

from main import BASH_TOOL, MAX_TOOL_ROUNDS, run_bash


load_dotenv()

app = Flask(__name__)
client = OpenAI(
    base_url=os.environ["BASE_URL"],
    api_key=os.environ["API_KEY"],
)
model = os.environ["MODEL"]
system_prompt = Path("system_prompt.md").read_text().strip()
lock = Lock()

messages = [{"role": "system", "content": system_prompt}]
pending_calls = []
tool_rounds = 0


def usage_dict(usage) -> dict:
    details = usage.prompt_tokens_details
    cached = details.cached_tokens if details and details.cached_tokens is not None else 0
    return {
        "input": usage.prompt_tokens,
        "cached": cached,
        "output": usage.completion_tokens,
    }


def pending_event() -> dict:
    call = pending_calls[0]
    try:
        command = json.loads(call.function.arguments)["command"]
    except (json.JSONDecodeError, KeyError, TypeError):
        command = call.function.arguments
    return {"type": "approval", "tool_call_id": call.id, "command": command}


def advance_agent() -> list[dict]:
    global pending_calls, tool_rounds
    events = []

    while tool_rounds < MAX_TOOL_ROUNDS:
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=[BASH_TOOL],
        )
        events.append({"type": "usage", **usage_dict(response.usage)})
        assistant = response.choices[0].message
        messages.append(assistant.model_dump(exclude_none=True))

        if not assistant.tool_calls:
            events.append({"type": "assistant", "content": assistant.content or ""})
            return events

        tool_rounds += 1
        pending_calls = list(assistant.tool_calls)
        events.append(pending_event())
        return events

    events.append(
        {
            "type": "assistant",
            "content": f"Stopped after {MAX_TOOL_ROUNDS} tool rounds.",
        }
    )
    return events


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/chat")
def chat():
    global tool_rounds
    with lock:
        if pending_calls:
            return jsonify({"error": "Approve or deny the pending command first."}), 409
        content = (request.get_json(silent=True) or {}).get("message", "").strip()
        if not content:
            return jsonify({"error": "Message cannot be empty."}), 400
        messages.append({"role": "user", "content": content})
        tool_rounds = 0
        return jsonify({"events": advance_agent()})


@app.post("/api/decision")
def decision():
    global pending_calls
    with lock:
        if not pending_calls:
            return jsonify({"error": "There is no pending command."}), 409

        approved = bool((request.get_json(silent=True) or {}).get("approved"))
        call = pending_calls.pop(0)
        try:
            command = json.loads(call.function.arguments)["command"]
            result = run_bash(command) if approved else "The user declined to run this command."
        except (json.JSONDecodeError, KeyError, TypeError) as error:
            command = call.function.arguments
            result = f"Invalid bash arguments: {error}"

        messages.append(
            {"role": "tool", "tool_call_id": call.id, "content": result}
        )
        events = [
            {
                "type": "tool_result",
                "command": command,
                "approved": approved,
                "content": result,
            }
        ]
        if pending_calls:
            events.append(pending_event())
        else:
            events.extend(advance_agent())
        return jsonify({"events": events})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)

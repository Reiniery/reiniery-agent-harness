import json
import os
from pathlib import Path
from threading import Lock

from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request
from openai import OpenAI, APIError

from main import BASH_TOOL, MAX_TOOL_ROUNDS, MAX_OUTPUT_CHARS, execute_tool
from plugin_loader import Plugins


load_dotenv()

app = Flask(__name__)
client = OpenAI(
    base_url=os.environ["BASE_URL"],
    api_key=os.environ["API_KEY"],
)
model = os.environ["MODEL"]
system_prompt = Path("system_prompt.md").read_text().strip()
lock = Lock()
plugins = None

messages = [{"role": "system", "content": system_prompt}]
pending_calls = []
tool_rounds = 0


def usage_dict(usage) -> dict:
    if usage is None:
        return {"input": None, "cached": None, "output": None}
    details = usage.prompt_tokens_details
    cached = details.cached_tokens if details and details.cached_tokens is not None else 0
    return {
        "input": usage.prompt_tokens,
        "cached": cached,
        "output": usage.completion_tokens,
    }


def pending_event() -> dict:
    call = pending_calls[0]
    command = call_description(call)
    return {"type": "approval", "tool_call_id": call.id, "command": command}


def advance_agent() -> list[dict]:
    global pending_calls, tool_rounds
    events = []

    while tool_rounds < MAX_TOOL_ROUNDS:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                tools=[BASH_TOOL] + (plugins.tools if plugins else []),
            )
        except APIError as error:
            answer = f"Model request failed (HTTP {getattr(error, 'status_code', None) or 'connection error'}). Check MODEL and provider availability; retry when resolved."
            messages.append({"role": "assistant", "content": answer})
            events.append({"type": "assistant", "content": answer})
            return events
        events.append({"type": "usage", **usage_dict(response.usage)})
        assistant = response.choices[0].message
        messages.append(assistant.model_dump(exclude_none=True))

        if not assistant.tool_calls:
            events.append({"type": "assistant", "content": assistant.content or ""})
            return events

        tool_rounds += 1
        pending_calls = list(assistant.tool_calls)
        events.extend(drain_pending())
        if pending_calls:
            return events

    events.append(
        {
            "type": "assistant",
            "content": f"Stopped after {MAX_TOOL_ROUNDS} tool rounds.",
        }
    )
    return events


def call_description(call):
    try:
        args = json.loads(call.function.arguments)
        return args.get("command", "") if call.function.name == "bash" else f"{call.function.name}: {json.dumps(args)}"
    except (ValueError, TypeError, AttributeError):
        return call.function.arguments


def finish_call(call, approved):
    try:
        args = json.loads(call.function.arguments)
        if not isinstance(args, dict):
            raise ValueError("arguments must be an object")
        result = execute_tool(call.function.name, args, plugins) if approved else "The user declined; do not try another way."
    except (ValueError, TypeError) as error:
        result = f"Invalid tool arguments: {error}"
    result = result[:MAX_OUTPUT_CHARS]
    messages.append({"role":"tool", "tool_call_id":call.id, "content":result})
    return {"type":"tool_result", "command":call_description(call), "approved":approved, "content":result}


def drain_pending():
    events = []
    while pending_calls:
        call = pending_calls[0]
        if plugins is None or plugins.needs_approval(call.function.name):
            events.append(pending_event())
            break
        pending_calls.pop(0)
        events.append(finish_call(call, True))
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

        approved = (request.get_json(silent=True) or {}).get("approved") is True
        call = pending_calls.pop(0)
        events = [finish_call(call, approved)]
        if not approved:
            while pending_calls:
                events.append(finish_call(pending_calls.pop(0), False))
            answer = "Declined. I stopped this turn without running further tools."
            messages.append({"role":"assistant", "content":answer})
            events.append({"type":"assistant", "content":answer})
        else:
            events.extend(drain_pending())
            if not pending_calls:
                events.extend(advance_agent())
        return jsonify({"events":events})


if __name__ == "__main__":
    with Plugins(Path(__file__).parent) as active_plugins:
        plugins = active_plugins
        messages[0]["content"] += plugins.skill_prompt()
        app.run(host="127.0.0.1", port=8000, debug=False)

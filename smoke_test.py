import os

from dotenv import load_dotenv
from openai import OpenAI


load_dotenv()

base_url = os.environ.get("BASE_URL")
api_key = os.environ.get("API_KEY")
model = os.environ.get("MODEL")

if not all((base_url, api_key, model)):
    raise SystemExit("BASE_URL, API_KEY, and MODEL must all be set in .env")

client = OpenAI(base_url=base_url, api_key=api_key)

plain = client.chat.completions.create(
    model=model,
    messages=[{"role": "user", "content": "Reply with exactly: API works"}],
)
print("Plain response:", plain.choices[0].message.content)
print("Plain usage:", plain.usage)

bash_tool = {
    "type": "function",
    "function": {
        "name": "bash",
        "description": "Run a shell command on the user's computer.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The command to run."}
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
}

tool_test = client.chat.completions.create(
    model=model,
    messages=[
        {
            "role": "user",
            "content": "Call the bash tool with the command pwd. Do not answer in text.",
        }
    ],
    tools=[bash_tool],
    tool_choice="required",
)
tool_calls = tool_test.choices[0].message.tool_calls or []
if not tool_calls or tool_calls[0].function.name != "bash":
    raise SystemExit("The model did not return the required bash tool call")

print("Tool call:", tool_calls[0].function.name, tool_calls[0].function.arguments)
print("Tool usage:", tool_test.usage)
print("Smoke test passed.")

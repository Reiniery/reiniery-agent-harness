import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


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

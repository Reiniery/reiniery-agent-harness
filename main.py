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
    user_message = input("You: ")

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
    )

    print(f"Assistant: {response.choices[0].message.content}")
    show_usage(response.usage)


if __name__ == "__main__":
    main()

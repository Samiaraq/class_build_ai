
import sys

from classbuild.llm.groq_client import GroqClient
from classbuild.llm.exceptions import GroqClientError


SAMPLE_PROMPT = (
    "Explain what a Python variable is to a beginner "
    "in 3 bullet points."
)


def main():
    prompt = " ".join(sys.argv[1:]).strip() or SAMPLE_PROMPT

    try:
        client = GroqClient()

        print(f"Model: {client.model}")
        print(f"Prompt: {prompt}")

        response = client.generate(prompt)

        print("\n[OK]")
        print(response)

        return 0

    except GroqClientError as error:
        print(f"\n[FAILED] {error}")
        return 1


if __name__ == "__main__":
    sys.exit(main())

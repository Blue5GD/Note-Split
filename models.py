"""The only file that talks to the model.

Other files call call_model and get a string back. They do not import the
OpenAI library themselves. Stop is a sentence the page shows. ProviderError
is a failure message that came from the provider.
"""

import math
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from openai import OpenAI, OpenAIError

# A shell check and the Streamlit page both import this file, so both see .env.
load_dotenv()

MODEL = "gpt-6.1-sol"
MAX_OUTPUT_TOKENS = 65536


class Stop(Exception):
    """The page shows this exception's message and waits."""


class ProviderError(Exception):
    """The page shows the provider's message and waits."""


@dataclass
class TokenUsage:
    """Count the model's tokens for one run.

    The page keeps one of these while it works, then saves as_dict()
    with the finished run. A call that fails before the provider
    answers does not add tokens.
    """

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    @property
    def total_tokens(self) -> int:
        """Return both directions added together."""
        return self.input_tokens + self.output_tokens

    def add(self, response_usage) -> None:
        """Add the counts from one OpenAI response usage object.

        The call always counts. A field that is missing or None counts
        as zero, so an older response shape still works.
        """
        self.calls += 1
        if response_usage is None:
            return
        input_tokens = getattr(response_usage, "input_tokens", None)
        if input_tokens is not None:
            self.input_tokens += int(input_tokens)
        output_tokens = getattr(response_usage, "output_tokens", None)
        if output_tokens is not None:
            self.output_tokens += int(output_tokens)

    def as_dict(self) -> dict:
        """Return the counts as plain ints, ready to save."""
        return {
            "input_tokens": int(self.input_tokens),
            "output_tokens": int(self.output_tokens),
            "calls": int(self.calls),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TokenUsage":
        """Load a saved run. A missing key starts at zero."""
        # A saved run from an older version may not have every key. A
        # None or blank value also starts at zero.
        input_tokens = data.get("input_tokens") or 0
        output_tokens = data.get("output_tokens") or 0
        calls = data.get("calls") or 0
        return cls(
            input_tokens=int(input_tokens),
            output_tokens=int(output_tokens),
            calls=int(calls),
        )


def estimate_cost(usage: TokenUsage) -> float | None:
    """Return a USD estimate, or None when prices are not set.

    INPUT_PRICE_PER_MTOK and OUTPUT_PRICE_PER_MTOK are read from the
    environment. Each is a price in USD per million tokens. Both must
    be present, finite, and not negative, or there is no estimate.
    """
    input_price = _price("INPUT_PRICE_PER_MTOK")
    output_price = _price("OUTPUT_PRICE_PER_MTOK")
    if input_price is None or output_price is None:
        return None
    return (usage.input_tokens / 1e6) * input_price + (
        usage.output_tokens / 1e6
    ) * output_price


def format_cost(cost: float | None) -> str:
    """Return a short USD string, or an empty string for no estimate.

    A small positive estimate that would round to $0.0000 is shown as
    "<$0.0001" instead, so the line does not look free.
    """
    if cost is None:
        return ""
    if cost == 0:
        return "$0.00"
    if cost >= 1:
        return f"${cost:.2f}"
    if cost < 0.0001:
        return "<$0.0001"
    return f"${cost:.4f}"


def _price(name: str) -> float | None:
    # A missing or malformed price means "do not show a cost". A
    # negative or infinite price is not a real price either.
    value = os.environ.get(name)
    if value is None or value.strip() == "":
        return None
    try:
        price = float(value)
    except ValueError:
        return None
    if not math.isfinite(price) or price < 0:
        return None
    return price


def call_model(
    text: str,
    *,
    response_schema: dict | None = None,
    response_name: str = "result",
    usage: TokenUsage | None = None,
) -> str:
    """Send text to the model and return the reply text.

    response_schema asks for structured output. The reply is still a
    string, but it holds JSON that follows that schema. response_name
    labels the schema for the provider. usage, when given, collects the
    token counts from this call. A cut-off reply still counts.
    """
    # Read the key here, on every call, before any request is sent.
    provider = os.environ.get("PROVIDER")
    api_key = os.environ.get("API_KEY")
    if provider is None or provider != "openai":
        raise Stop("Set PROVIDER to openai in the .env file.")
    if api_key is None or api_key.strip() == "":
        raise Stop("Set API_KEY in the .env file.")

    # max_retries=0 keeps the SDK from resending a failed request behind
    # the page's back. The page already treats a provider error as final,
    # and a hidden retry could spend credits that the call caption does
    # not show.
    client = OpenAI(api_key=api_key, max_retries=0)
    # The Responses API takes a JSON schema through text.format. This is
    # not the response_format parameter from Chat Completions.
    # store=False asks the provider not to keep this response for later
    # retrieval. It does not change the reply.
    request = {
        "model": MODEL,
        "input": text,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "store": False,
    }
    if response_schema is not None:
        request["text"] = {
            "format": {
                "type": "json_schema",
                "name": response_name,
                "schema": response_schema,
                "strict": True,
            }
        }
    try:
        response = client.responses.create(**request)
    except OpenAIError as exc:
        message = getattr(exc, "message", None)
        if not isinstance(message, str) or message.strip() == "":
            message = str(exc)
        raise ProviderError(message) from exc

    # Count the call before the status checks. A cut-off reply was still
    # paid work, and a response with no usage object still made a call.
    if usage is not None:
        usage.add(response.usage)

    # A cut-off reply is unfinished. Drop it. Do not read the partial text.
    reason = None
    if response.incomplete_details is not None:
        reason = response.incomplete_details.reason
    if response.status == "incomplete" and reason == "max_output_tokens":
        raise Stop(
            "The reply was cut off because it hit the output-token limit."
        )

    # failed, incomplete for any other reason, or any status besides completed.
    # Do not read the reply body.
    if response.status != "completed":
        raise ProviderError(_provider_message(response))

    return response.output_text


def _provider_message(response) -> str:
    error = response.error
    if error is not None and error.message.strip() != "":
        return error.message
    status = response.status if response.status else "unknown"
    return f"The model returned status {status}."

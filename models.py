"""The only file that talks to the model.

Other files call call_model and get a string back. They do not import the
OpenAI library themselves. Stop is a sentence the page shows. ProviderError
is a failure message that came from the provider.
"""

import base64
import os

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


def call_model(text: str, images: list[dict] | None = None) -> str:
    """Send text to the model and return the reply text.

    images is only for a photo page. Each item is a dict:
        {"data": image_bytes, "media_type": "image/jpeg"}
    media_type is "image/png" or "image/jpeg". Other calls leave images out.
    """
    # Read the key here, on every call, before any request is sent.
    provider = os.environ.get("PROVIDER")
    api_key = os.environ.get("API_KEY")
    if provider is None or provider != "openai":
        raise Stop("Set PROVIDER to openai in the .env file.")
    if api_key is None or api_key.strip() == "":
        raise Stop("Set API_KEY in the .env file.")

    client = OpenAI(api_key=api_key)
    try:
        response = client.responses.create(
            model=MODEL,
            input=_input(text, images),
            max_output_tokens=MAX_OUTPUT_TOKENS,
        )
    except OpenAIError as exc:
        message = getattr(exc, "message", None)
        if not isinstance(message, str) or message.strip() == "":
            message = str(exc)
        raise ProviderError(message) from exc

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


def _input(text: str, images: list[dict] | None):
    if not images:
        return text
    content = [{"type": "input_text", "text": text}]
    for image in images:
        encoded = base64.b64encode(image["data"]).decode("ascii")
        media_type = image["media_type"]
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{media_type};base64,{encoded}",
                "detail": "auto",
            }
        )
    return [{"role": "user", "content": content}]


def _provider_message(response) -> str:
    error = response.error
    if error is not None and error.message.strip() != "":
        return error.message
    status = response.status if response.status else "unknown"
    return f"The model returned status {status}."

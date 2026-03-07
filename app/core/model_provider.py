"""LLM model provider.

Selects the LLM backend at startup based on environment variables:
  - OPENAI_API_KEY set  → OpenAI (priority)
  - GEMINI_API_KEY set  → Gemini via OpenAI-compatible endpoint (fallback)
  - Neither set         → raises ValueError

Exposes a single ``llm_model`` object consumed by ``ChatAgent``.
"""

import logging

import openai
from agents import (
    OpenAIChatCompletionsModel,
    set_default_openai_api,
    set_tracing_disabled,
)

from app.utils.config import settings

logger = logging.getLogger(__name__)

set_tracing_disabled(True)
set_default_openai_api("chat_completions")


def _build_model() -> OpenAIChatCompletionsModel:
    if settings.OPENAI_API_KEY:
        logger.info("LLM provider: OpenAI (%s)", settings.OPENAI_MODEL)
        client = openai.AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        return OpenAIChatCompletionsModel(
            model=settings.OPENAI_MODEL, openai_client=client
        )

    if settings.GEMINI_API_KEY:
        logger.info("LLM provider: Gemini (%s)", settings.GEMINI_MODEL)
        client = openai.AsyncOpenAI(
            api_key=settings.GEMINI_API_KEY,
            base_url=settings.GEMINI_API_URL,
        )
        return OpenAIChatCompletionsModel(
            model=settings.GEMINI_MODEL, openai_client=client
        )

    raise ValueError(
        "No LLM API key configured. Set OPENAI_API_KEY (preferred) or GEMINI_API_KEY."
    )


llm_model = _build_model()

__all__ = ["llm_model"]

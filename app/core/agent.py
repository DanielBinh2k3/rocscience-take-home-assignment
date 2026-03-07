"""AI agent service.

SSE event types produced:
    agent.message.delta   – text chunk arriving from the model
    agent.message.done    – full response complete; carries session_id
    agent.workflow.failed – unhandled exception
"""

import logging
import uuid

from agents import Agent, ItemHelpers, ModelSettings, Runner
from openai.types.responses import ResponseTextDeltaEvent

from app.utils.serializer import make_sse_event

from .model_provider import llm_model

logger = logging.getLogger(__name__)

_INSTRUCTIONS = (
    "You are a helpful, friendly, and concise AI assistant. "
    "Answer clearly and accurately. If you don't know something, say so."
)

# {"role": "user"|"assistant", "content": str}
HistoryMessage = dict[str, str]


class ChatAgent:
    def __init__(self) -> None:
        self._agent = Agent(
            name="AI Assistant",
            instructions=_INSTRUCTIONS,
            model=llm_model,
            model_settings=ModelSettings(temperature=0.7, top_p=0.9),
        )

    async def stream_response(
        self,
        user_message: str,
        history: list[HistoryMessage],
        session_id: uuid.UUID,
        result_holder: list[str] | None = None,
    ):
        """Async generator that yields SSE-formatted strings.

        Args:
            user_message:  The current user's message.
            history:       Prior conversation turns (excluding the current message).
            session_id:    Echoed back in the ``agent.message.done`` payload per spec.
            result_holder: If provided, the full assistant response is appended here
                           after streaming completes so callers can persist it without
                           re-parsing SSE strings.

        Yields:
            SSE strings ready to be forwarded via FastAPI StreamingResponse.
        """
        messages = history + [{"role": "user", "content": user_message}]
        full_response = ""

        try:
            result = Runner.run_streamed(self._agent, input=messages)

            async for event in result.stream_events():
                if event.type == "raw_response_event" and isinstance(
                    event.data, ResponseTextDeltaEvent
                ):
                    chunk = event.data.delta
                    full_response += chunk
                    yield make_sse_event("agent.message.delta", {"text": chunk})

                elif event.type == "run_item_stream_event":
                    if event.item.type == "message_output_item":
                        full_response = ItemHelpers.text_message_output(event.item)

        except Exception as exc:
            logger.exception("Agent run failed: %s", exc)
            yield make_sse_event("agent.workflow.failed", {"error": str(exc)})
            return

        if result_holder is not None:
            result_holder.append(full_response)

        yield make_sse_event("agent.message.done", {"session_id": str(session_id)})


# Module-level singleton – import and use directly
agent = ChatAgent()

import json
from typing import Any


def make_sse_event(event: str, data: dict[str, Any]) -> str:
    """Format a Server-Sent Event string.

    Wire format:
        event: <event_name>\\n
        data: <json_payload>\\n
        \\n
    """
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

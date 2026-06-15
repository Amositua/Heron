import json
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal["stage_change", "file_written", "validation_step", "mcp_action", "complete", "error"]


class BuildEvent(BaseModel):
    type: EventType
    data: dict[str, Any]

    def to_sse(self) -> str:
        return f"event: {self.type}\ndata: {json.dumps(self.data)}\n\n"

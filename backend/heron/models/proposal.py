import uuid
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field


class Proposal(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    app_name: str
    change_type: Literal["alert_threshold", "spl_rewrite", "panel_add", "schema_update"]
    target: dict[str, Any]
    current_value: Any
    proposed_value: Any
    rationale: str
    risk_level: Literal["low", "medium", "high"]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    status: Literal["pending", "approved", "rejected", "applied"] = "pending"

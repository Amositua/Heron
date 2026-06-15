from typing import Any, Literal

from pydantic import BaseModel


class RoutingDecision(BaseModel):
    proposal_id: str
    action: Literal["auto_apply", "queue_for_review"]
    reason: str


class ApplyResult(BaseModel):
    success: bool
    proposal_id: str
    app_name: str
    before_version: int | None = None
    after_version: int | None = None
    changelog_message: str | None = None
    error: str | None = None


class RollbackResult(BaseModel):
    success: bool
    app_name: str
    restored_version: int | None = None
    new_version: int | None = None
    changelog_message: str | None = None
    error: str | None = None


class ChangelogEntry(BaseModel):
    id: int
    proposal_id: str | None
    app_name: str
    change_type: str
    target: dict[str, Any]
    previous_value: Any
    new_value: Any
    message: str
    before_version: int
    after_version: int
    applied_at: str
    rolled_back: bool


class AppSummary(BaseModel):
    app_name: str
    current_version: int
    last_changed_at: str

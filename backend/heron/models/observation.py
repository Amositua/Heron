from datetime import datetime

from pydantic import BaseModel, Field


class AlertStats(BaseModel):
    alert_name: str
    search_name: str
    firing_count: int
    expected_count: int
    noise_ratio: float
    observed_event_rate: float
    current_threshold: float
    alert_comparator: str
    window_minutes: float


class ObservationReport(BaseModel):
    app_name: str
    timestamp: datetime
    alert_stats: list[AlertStats]
    search_perf: list = Field(default_factory=list)
    schema_state: dict = Field(default_factory=lambda: {"status": "not_implemented_v1"})
    dashboard_usage: list = Field(default_factory=list)
    gap_signals: list = Field(default_factory=list)

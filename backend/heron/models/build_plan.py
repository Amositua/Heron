from typing import Literal

from pydantic import BaseModel


class FieldExtraction(BaseModel):
    name: str
    type: str
    extraction: str


class DataSource(BaseModel):
    sourcetype: str
    parsing_strategy: str
    fields_extracted: list[FieldExtraction]
    input_path: str


class SavedSearch(BaseModel):
    name: str
    spl: str
    schedule: str
    description: str


class DashboardPanel(BaseModel):
    title: str
    search_name: str
    viz_type: Literal["line", "bar", "table", "single_value", "area", "column"]


class Dashboard(BaseModel):
    name: str
    panels: list[DashboardPanel]


class Alert(BaseModel):
    name: str
    search_name: str
    threshold_condition: str
    severity: Literal["info", "low", "medium", "high"]
    action: str


class BuildPlan(BaseModel):
    app_name: str
    app_description: str
    data_source: DataSource
    saved_searches: list[SavedSearch]
    dashboards: list[Dashboard]
    alerts: list[Alert]
    notes: str

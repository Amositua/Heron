import re
import uuid
from pathlib import Path

import jinja2

from heron.models.build_plan import Alert, BuildPlan, Dashboard, SavedSearch
from heron.models.build_result import BuildResult

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"

_VIZ_ELEMENT_MAP: dict[str, tuple[str, str | None]] = {
    "line": ("chart", "line"),
    "area": ("chart", "area"),
    "bar": ("chart", "bar"),
    "column": ("chart", "column"),
    "table": ("table", None),
    "single_value": ("single", None),
}

_SEVERITY_MAP = {"info": "1", "low": "2", "medium": "3", "high": "4"}


class Builder:
    def __init__(self) -> None:
        self._env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(TEMPLATES_DIR)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

    def build(self, plan: BuildPlan, output_root: str) -> BuildResult:
        warnings: list[str] = []
        if not plan.app_description.strip():
            warnings.append("app_description is empty")

        app_dir, default_dir, views_dir, metadata_dir = _make_app_dirs(output_root, plan.app_name)

        alert_by_search, alert_warnings = _map_alerts_to_searches(plan)
        warnings.extend(alert_warnings)

        context = _build_context(plan, alert_by_search)

        files_created = self._render_conf_files(context, default_dir, metadata_dir, app_dir)
        dashboard_files, dashboard_warnings = self._render_dashboards(plan, context, views_dir)
        files_created.extend(dashboard_files)
        warnings.extend(dashboard_warnings)

        return BuildResult(
            app_path=str(app_dir),
            files_created=files_created,
            warnings=warnings,
            build_id=str(uuid.uuid4()),
        )

    def _render_conf_files(
        self, context: dict, default_dir: Path, metadata_dir: Path, app_dir: Path
    ) -> list[str]:
        return [
            self._render("app.conf.j2", context, default_dir / "app.conf"),
            self._render("inputs.conf.j2", context, default_dir / "inputs.conf"),
            self._render("props.conf.j2", context, default_dir / "props.conf"),
            self._render("transforms.conf.j2", context, default_dir / "transforms.conf"),
            self._render("savedsearches.conf.j2", context, default_dir / "savedsearches.conf"),
            self._render("metadata_default.meta.j2", context, metadata_dir / "default.meta"),
            self._render("README.md.j2", context, app_dir / "README.md"),
        ]

    def _render_dashboards(
        self, plan: BuildPlan, context: dict, views_dir: Path
    ) -> tuple[list[str], list[str]]:
        files: list[str] = []
        warnings: list[str] = []
        searches_by_name = {s.name: s for s in plan.saved_searches}
        for dashboard in plan.dashboards:
            panels, panel_warnings = _build_panels(dashboard, searches_by_name)
            warnings.extend(panel_warnings)
            dashboard_context = {**context, "dashboard_label": _title_case(dashboard.name), "panels": panels}
            files.append(
                self._render("dashboard.xml.j2", dashboard_context, views_dir / f"{dashboard.name}.xml")
            )
        return files, warnings

    def _render(self, template_name: str, context: dict, dest: Path) -> str:
        template = self._env.get_template(template_name)
        dest.write_text(template.render(**context), encoding="utf-8")
        return str(dest)


def _make_app_dirs(output_root: str, app_name: str) -> tuple[Path, Path, Path, Path]:
    app_dir = Path(output_root) / app_name
    default_dir = app_dir / "default"
    views_dir = default_dir / "data" / "ui" / "views"
    metadata_dir = app_dir / "metadata"
    for directory in (default_dir, views_dir, metadata_dir):
        directory.mkdir(parents=True, exist_ok=True)
    return app_dir, default_dir, views_dir, metadata_dir


def _map_alerts_to_searches(plan: BuildPlan) -> tuple[dict[str, Alert], list[str]]:
    search_names = {s.name for s in plan.saved_searches}
    alert_by_search: dict[str, Alert] = {}
    warnings: list[str] = []
    for alert in plan.alerts:
        if alert.search_name not in search_names:
            warnings.append(f"alert '{alert.name}' references unknown search '{alert.search_name}'")
        else:
            alert_by_search[alert.search_name] = alert
    return alert_by_search, warnings


def _build_context(plan: BuildPlan, alert_by_search: dict[str, Alert]) -> dict:
    return {
        "plan": plan,
        "app_label": _title_case(plan.app_name),
        "fields": plan.data_source.fields_extracted,
        "transform_names": [f"extract_{f.name}" for f in plan.data_source.fields_extracted],
        "saved_searches": [
            {
                "search": search,
                "cron_schedule": _schedule_to_cron(search.schedule),
                "alert_config": _alert_config(alert_by_search[search.name])
                if search.name in alert_by_search
                else None,
            }
            for search in plan.saved_searches
        ],
    }


def _build_panels(
    dashboard: Dashboard, searches_by_name: dict[str, SavedSearch]
) -> tuple[list[dict], list[str]]:
    panels: list[dict] = []
    warnings: list[str] = []
    for panel in dashboard.panels:
        search = searches_by_name.get(panel.search_name)
        if search is None:
            warnings.append(
                f"dashboard panel '{panel.title}' references unknown search '{panel.search_name}'"
            )
            continue
        element, chart_type = _VIZ_ELEMENT_MAP.get(panel.viz_type, ("table", None))
        panels.append({"panel": panel, "search": search, "element": element, "chart_type": chart_type})
    return panels, warnings


def _title_case(name: str) -> str:
    return name.replace("_", " ").replace("-", " ").title()


def _schedule_to_cron(schedule: str) -> str:
    match = re.match(r"(\d+)\s*([mh])", schedule.strip().lower())
    if not match:
        return "*/5 * * * *"
    value, unit = match.groups()
    if unit == "h":
        return f"0 */{value} * * *"
    return f"*/{value} * * * *"


def _alert_config(alert: Alert) -> dict[str, str]:
    numbers = re.findall(r"\d+", alert.threshold_condition)
    quantity = numbers[0] if numbers else "5"
    window_minutes = numbers[1] if len(numbers) > 1 else "10"
    relation = (
        "less than"
        if re.search(r"less than|fewer than", alert.threshold_condition, re.I)
        else "greater than"
    )
    return {
        "severity": _SEVERITY_MAP.get(alert.severity, "3"),
        "quantity": quantity,
        "relation": relation,
        "earliest_time": f"-{window_minutes}m",
    }

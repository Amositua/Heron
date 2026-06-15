import logging
import re
from datetime import datetime, timezone

from heron.models.observation import AlertStats, ObservationReport
from heron.splunk.splunk_client import SplunkClient

logger = logging.getLogger(__name__)

RESTART_SOURCETYPE = "kubernetes:events"
RESTART_NAMESPACE = "payments"
DEFAULT_WINDOW_MINUTES = 10.0
NOISE_RATIO_CAP = 100.0
HOURS_PER_DAY = 24


class Observer:
    def __init__(self, splunk_client: SplunkClient) -> None:
        self._splunk = splunk_client

    async def observe_app(self, app_name: str) -> ObservationReport:
        alert_stats = [self._observe_alert(alert) for alert in self._splunk.list_alerts(app_name)]

        return ObservationReport(
            app_name=app_name,
            timestamp=datetime.now(timezone.utc),
            alert_stats=alert_stats,
            search_perf=self.search_perf(app_name),
            schema_state=self.schema_state(app_name),
            dashboard_usage=self.dashboard_usage(app_name),
            gap_signals=self.gap_signals(app_name),
        )

    def _observe_alert(self, alert: dict) -> AlertStats:
        window_minutes = _parse_window_minutes(alert.get("earliest_time"))
        threshold = float(alert.get("alert_threshold") or 0)

        firing_count = len(self._splunk.get_alert_firing_history(alert["name"], count=1000))
        observed_event_rate = self._observed_restart_rate_per_minute(window_minutes)

        expected_per_window = observed_event_rate * window_minutes
        if threshold > 0 and expected_per_window > threshold:
            expected_count = round((HOURS_PER_DAY * 60) / window_minutes)
        else:
            expected_count = 0

        if threshold > 0:
            noise_ratio = min(expected_per_window / threshold, NOISE_RATIO_CAP)
        else:
            noise_ratio = NOISE_RATIO_CAP if expected_per_window > 0 else 0.0

        return AlertStats(
            alert_name=alert["name"],
            search_name=alert["name"],
            firing_count=firing_count,
            expected_count=expected_count,
            noise_ratio=noise_ratio,
            observed_event_rate=observed_event_rate,
            current_threshold=threshold,
            alert_comparator=alert.get("alert_comparator") or "greater than",
            window_minutes=window_minutes,
        )

    def _observed_restart_rate_per_minute(self, window_minutes: float) -> float:
        results = self._splunk.run_search(
            f'sourcetype="{RESTART_SOURCETYPE}" namespace="{RESTART_NAMESPACE}" event_type="restart" '
            "| stats count as restarts",
            earliest_time=f"-{window_minutes:g}m",
            latest_time="now",
        )
        if not results:
            return 0.0
        restarts = float(results[0].get("restarts", 0))
        return restarts / window_minutes

    def search_perf(self, app_name: str) -> list:
        logger.info("search_perf not implemented for v1", extra={"app_name": app_name})
        return []

    def schema_state(self, app_name: str) -> dict:
        logger.info("schema_state not implemented for v1", extra={"app_name": app_name})
        return {"status": "not_implemented_v1"}

    def dashboard_usage(self, app_name: str) -> list:
        logger.info("dashboard_usage not implemented for v1", extra={"app_name": app_name})
        return []

    def gap_signals(self, app_name: str) -> list:
        logger.info("gap_signals not implemented for v1", extra={"app_name": app_name})
        return []


def _parse_window_minutes(earliest_time: str | None) -> float:
    if not earliest_time:
        return DEFAULT_WINDOW_MINUTES
    match = re.match(r"^-(\d+(?:\.\d+)?)([smh])$", earliest_time)
    if not match:
        return DEFAULT_WINDOW_MINUTES
    value, unit = match.groups()
    value = float(value)
    if unit == "s":
        return value / 60.0
    if unit == "h":
        return value * 60.0
    return value

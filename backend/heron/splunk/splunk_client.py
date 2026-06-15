import os
from pathlib import Path
from typing import Any

import splunklib.client as splunklib_client
import splunklib.results as splunklib_results
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)


class SplunkClientError(Exception):
    """Raised when a read-only Splunk operation fails."""


class SplunkClient:
    """Read-only access to Splunk via the Splunk Python SDK.

    All writes happen through SplunkMCPClient; this class only ever
    issues GET-equivalent operations (searches, app/saved-search lookups).
    """

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        self._host = host or os.environ.get("SPLUNK_HOST", "localhost")
        self._port = int(port or os.environ.get("SPLUNK_PORT", "8089"))
        self._username = username or os.environ["SPLUNK_USERNAME"]
        self._password = password or os.environ["SPLUNK_PASSWORD"]
        self._service: splunklib_client.Service | None = None

    def _connect(self) -> splunklib_client.Service:
        if self._service is None:
            self._service = splunklib_client.connect(
                host=self._host,
                port=self._port,
                username=self._username,
                password=self._password,
            )
        return self._service

    def verify_app_installed(self, app_name: str) -> bool:
        service = self._connect()
        return app_name in service.apps

    def run_search(
        self,
        query: str,
        earliest_time: str = "-15m",
        latest_time: str = "now",
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        service = self._connect()
        spl = query.strip()
        if not spl.startswith("|") and not spl.lower().startswith("search"):
            spl = f"search {spl}"

        job = service.jobs.create(
            spl, earliest_time=earliest_time, latest_time=latest_time, exec_mode="blocking"
        )
        try:
            results: list[dict[str, Any]] = []
            reader = splunklib_results.JSONResultsReader(
                job.results(output_mode="json", count=max_results)
            )
            for result in reader:
                if isinstance(result, dict):
                    results.append(result)
            return results
        finally:
            job.cancel()

    def verify_data_flowing(self, sourcetype: str, earliest_time: str = "-5m") -> bool:
        results = self.run_search(
            f'search sourcetype="{sourcetype}" | head 1',
            earliest_time=earliest_time,
            latest_time="now",
            max_results=1,
        )
        return len(results) > 0

    def verify_search_returns(self, query: str, earliest_time: str = "-24h") -> bool:
        try:
            self.run_search(query, earliest_time=earliest_time, latest_time="now")
            return True
        except Exception:
            return False

    def get_alert_firing_history(self, alert_name: str, count: int = 50) -> list[dict[str, Any]]:
        service = self._connect()
        try:
            saved_search = service.saved_searches[alert_name]
        except KeyError as exc:
            raise SplunkClientError(f"Saved search '{alert_name}' not found") from exc

        try:
            alert_groups = saved_search.fired_alerts
        except Exception:
            return []

        history: list[dict[str, Any]] = []
        for group in alert_groups:
            for alert in group.alerts:
                if len(history) >= count:
                    return history
                content = alert.content
                history.append(
                    {
                        "sid": alert.name,
                        "trigger_time": content.get("trigger_time"),
                        "severity": content.get("severity"),
                        "expiration_time": content.get("expiration_time"),
                    }
                )
        return history

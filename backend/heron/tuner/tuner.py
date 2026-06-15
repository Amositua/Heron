import json
import logging
import re

from google import genai
from google.genai import types
from pydantic import BaseModel

from heron.models.observation import AlertStats, ObservationReport
from heron.models.proposal import Proposal

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"
TEMPERATURE = 0.2
LOW_RISK_CHANGE_THRESHOLD = 0.5
NOISE_RATIO_THRESHOLD = 3.0

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")

SYSTEM_PROMPT = """You are the Tuner component of Heron, an autonomous agent that maintains \
Splunk apps in production. You are given statistics about an alert that is firing far more \
often than expected (it is too noisy). Propose a new numeric threshold that would make the \
alert fire only on genuine spikes, and write a short, human-readable engineering rationale \
that references the actual numbers you were given.

Output ONLY a single JSON object with this exact shape, no markdown fences, no commentary:
{"proposed_threshold": <number>, "rationale": "<string>"}
"""


class TunerError(Exception):
    """Raised when the Tuner cannot produce a Gemini-backed proposal."""


class _ThresholdProposal(BaseModel):
    proposed_threshold: float
    rationale: str


class Tuner:
    def __init__(self, gemini_client: genai.Client) -> None:
        self._client = gemini_client

    async def propose_changes(self, app_name: str, report: ObservationReport) -> list[Proposal]:
        proposals: list[Proposal] = []

        for alert in report.alert_stats:
            proposal = await self._propose_for_alert(app_name, alert)
            if proposal is not None:
                proposals.append(proposal)

        proposals.extend(self._propose_from_search_perf(app_name, report.search_perf))
        proposals.extend(self._propose_from_schema_state(app_name, report.schema_state))
        proposals.extend(self._propose_from_dashboard_usage(app_name, report.dashboard_usage))
        proposals.extend(self._propose_from_gap_signals(app_name, report.gap_signals))

        return proposals

    async def _propose_for_alert(self, app_name: str, alert: AlertStats) -> Proposal | None:
        if alert.noise_ratio > NOISE_RATIO_THRESHOLD:
            return await self._propose_raise_threshold(app_name, alert)

        if alert.firing_count == 0 and alert.observed_event_rate > 0:
            return self._propose_lower_threshold(app_name, alert)

        return None

    async def _propose_raise_threshold(self, app_name: str, alert: AlertStats) -> Proposal:
        expected_per_window = alert.observed_event_rate * alert.window_minutes
        prompt = (
            f"Alert name: {alert.alert_name}\n"
            f"Condition: fires when the count is {alert.alert_comparator} "
            f"{alert.current_threshold:g} within a {alert.window_minutes:g}-minute window.\n"
            f"It fired {alert.firing_count} times in the last 24h "
            f"(a healthy alert would fire roughly {alert.expected_count} times in 24h).\n"
            f"The observed event rate is {alert.observed_event_rate:.2f} per minute, "
            f"i.e. roughly {expected_per_window:.1f} events per "
            f"{alert.window_minutes:g}-minute window."
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    temperature=TEMPERATURE,
                    response_mime_type="application/json",
                ),
            )
        except Exception as exc:
            raise TunerError(f"Gemini request failed: {exc}") from exc

        text = response.text
        if not text:
            raise TunerError("Gemini returned an empty response")

        try:
            data = json.loads(_strip_fences(text))
            parsed = _ThresholdProposal.model_validate(data)
        except Exception as exc:
            raise TunerError(f"Gemini response was not a valid threshold proposal: {exc}") from exc

        risk_level = _risk_level(alert.current_threshold, parsed.proposed_threshold)

        return Proposal(
            app_name=app_name,
            change_type="alert_threshold",
            target={"alert_name": alert.alert_name, "field": "alert_threshold"},
            current_value=alert.current_threshold,
            proposed_value=parsed.proposed_threshold,
            rationale=parsed.rationale,
            risk_level=risk_level,
        )

    def _propose_lower_threshold(self, app_name: str, alert: AlertStats) -> Proposal:
        expected_per_window = alert.observed_event_rate * alert.window_minutes
        proposed = round(expected_per_window, 1)
        if proposed <= 0 or proposed >= alert.current_threshold:
            proposed = max(1.0, alert.current_threshold / 2)

        rationale = (
            f"Alert '{alert.alert_name}' has not fired in the last 24h, but the observed "
            f"pod restart rate in the payments namespace is "
            f"{alert.observed_event_rate:.2f}/min (~{expected_per_window:.1f} events per "
            f"{alert.window_minutes:g}-minute window). Recommend lowering the threshold from "
            f"{alert.current_threshold:g} to {proposed:g} so the alert remains a meaningful "
            "signal."
        )

        return Proposal(
            app_name=app_name,
            change_type="alert_threshold",
            target={"alert_name": alert.alert_name, "field": "alert_threshold"},
            current_value=alert.current_threshold,
            proposed_value=proposed,
            rationale=rationale,
            risk_level="medium",
        )

    def _propose_from_search_perf(self, app_name: str, search_perf: list) -> list[Proposal]:
        logger.info("search_perf-based proposals not implemented for v1", extra={"app_name": app_name})
        return []

    def _propose_from_schema_state(self, app_name: str, schema_state: dict) -> list[Proposal]:
        logger.info("schema_state-based proposals not implemented for v1", extra={"app_name": app_name})
        return []

    def _propose_from_dashboard_usage(self, app_name: str, dashboard_usage: list) -> list[Proposal]:
        logger.info("dashboard_usage-based proposals not implemented for v1", extra={"app_name": app_name})
        return []

    def _propose_from_gap_signals(self, app_name: str, gap_signals: list) -> list[Proposal]:
        logger.info("gap_signals-based proposals not implemented for v1", extra={"app_name": app_name})
        return []


def _risk_level(current: float, proposed: float) -> str:
    if current == 0:
        return "low" if proposed == 0 else "medium"
    pct_change = abs(proposed - current) / abs(current)
    return "low" if pct_change <= LOW_RISK_CHANGE_THRESHOLD else "medium"


def _strip_fences(text: str) -> str:
    text = text.strip()
    return _FENCE_RE.sub("", text).strip()

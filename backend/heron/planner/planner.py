import json
import os
import re
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import ValidationError

from heron.models.build_plan import BuildPlan

load_dotenv(Path(__file__).resolve().parents[2] / ".env")

MODEL_NAME = "gemini-2.5-flash"
TEMPERATURE = 0.2

_FENCE_RE = re.compile(r"^```[a-zA-Z]*\n?|\n?```$")

SYSTEM_PROMPT = f"""You are the Planner component of Heron, an autonomous agent that \
designs, builds, deploys, and maintains Splunk apps for monitoring and analysis use cases.

Given a natural-language description of a monitoring need, emit a single JSON object \
that strictly matches the following JSON Schema. Output ONLY the JSON object — no \
markdown fences, no commentary, no extra top-level fields.

JSON Schema:
{json.dumps(BuildPlan.model_json_schema(), indent=2)}

Guidance for Kubernetes pod-monitoring requests (the primary use case Heron handles today):
- data_source.sourcetype must be "kubernetes:events".
- data_source.parsing_strategy should describe extracting fields from JSON-formatted \
Kubernetes event records (e.g. "json").
- data_source.input_path must be a single file path to a newline-delimited JSON event \
log (e.g. "/var/log/heron/k8s_events.json") — this is a synthetic data stream Splunk \
monitors, not a directory glob.
- data_source.fields_extracted must include exactly these five fields, using exactly \
these names: "pod_name", "namespace", "event_type", "restart_count", "timestamp". \
Additional fields may be added if useful, but these five are mandatory and must keep \
these exact names since later pipeline stages depend on them.
- saved_searches must contain exactly 4 SPL searches, in this order: (1) pod restarts \
over time (timechart of restart_count by pod_name), (2) top restarting pods (stats sum \
of restart_count by pod_name, sorted descending), (3) restart rate by namespace (stats \
sum of restart_count by namespace), (4) time since last restart per pod (latest event \
timestamp per pod_name). All should filter to namespace="payments" where relevant to \
the user's request.
- dashboards must contain exactly one dashboard with exactly 4 panels, one per saved \
search in the same order, choosing viz_type appropriately (timechart -> "line" or \
"area", "top"/stats-by -> "bar"/"column"/"table", single aggregation -> "single_value").
- alerts must contain exactly one alert named to describe a pod restart spike (e.g. \
"Pod restart spike in payments namespace"). Its search_name must reference the "pod \
restarts over time" saved search (item 1 above). threshold_condition must be a clear, \
human-readable description of the condition from the user's request (e.g. "more than 5 \
restarts in a 10 minute window for any pod").

All SPL must be valid Splunk SPL. All identifiers used as file or directory names \
(app_name, sourcetype, field names, saved search names, dashboard names) must use \
lowercase snake_case with no spaces. Human-facing text (app_description, dashboard \
panel titles, saved search descriptions, alert names) may use normal capitalization \
and spaces.
"""


class PlannerError(Exception):
    """Raised when the Planner cannot produce a valid BuildPlan."""


class Planner:
    def __init__(self, api_key: str | None = None) -> None:
        key = api_key or os.environ.get("GEMINI_API_KEY")
        if not key:
            raise PlannerError("GEMINI_API_KEY is not set")
        self._client = genai.Client(api_key=key)

    async def plan(self, user_prompt: str) -> BuildPlan:
        config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=TEMPERATURE,
            response_mime_type="application/json",
        )

        try:
            response = await self._client.aio.models.generate_content(
                model=MODEL_NAME,
                contents=user_prompt,
                config=config,
            )
        except Exception as exc:
            raise PlannerError(f"Gemini request failed: {exc}") from exc

        text = response.text
        if not text:
            raise PlannerError("Gemini returned an empty response")

        cleaned = _strip_fences(text)

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise PlannerError(f"Gemini response was not valid JSON: {exc}") from exc

        try:
            return BuildPlan.model_validate(data)
        except ValidationError as exc:
            raise PlannerError(
                f"Gemini response did not match the BuildPlan schema: {exc}"
            ) from exc


def _strip_fences(text: str) -> str:
    text = text.strip()
    return _FENCE_RE.sub("", text).strip()

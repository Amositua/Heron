import asyncio
import configparser
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from google import genai

from heron.approver.approver import APP_ROOT, SAVEDSEARCHES_CONF, Approver, _format_conf_number, _read_app_files
from heron.deployer.deployer import Deployer
from heron.deployer.validators import validate_deployment
from heron.models.build_plan import Alert, BuildPlan, DataSource, FieldExtraction, SavedSearch
from heron.observer.observer import Observer
from heron.splunk.mcp_client import SplunkMCPClient
from heron.splunk.splunk_client import SplunkClient
from heron.storage.db import DEFAULT_DB_PATH, DBClient
from heron.tuner.tuner import Tuner

APP_NAME = "payments_pod_monitoring"
APP_DIR = APP_ROOT / APP_NAME
PLAN_PATH = APP_ROOT / f"{APP_NAME}.plan.json"
DATA_FILE = Path("/var/log/heron/k8s_events.json")
GENERATOR_SCRIPT = Path(__file__).resolve().parent / "generate_k8s_data.py"
NOISY_DURATION_MINUTES = 2
INDEXING_BUFFER_SECONDS = 10
THRESHOLD_POLL_ATTEMPTS = 5
THRESHOLD_POLL_DELAY_SECONDS = 3


def _reconstruct_plan(app_dir: Path) -> BuildPlan:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read(app_dir / "default" / "savedsearches.conf")

    saved_searches: list[SavedSearch] = []
    alerts: list[Alert] = []
    for stanza in parser.sections():
        section = parser[stanza]
        saved_searches.append(
            SavedSearch(
                name=stanza,
                spl=section["search"],
                schedule=section.get("cron_schedule", ""),
                description=section.get("description", ""),
            )
        )
        if "quantity" in section:
            alerts.append(
                Alert(
                    name="Pod restart spike in payments namespace",
                    search_name=stanza,
                    threshold_condition=(
                        f"{section.get('relation', 'greater than')} {section['quantity']} "
                        f"restarts in {section.get('dispatch.earliest_time', '-10m')}"
                    ),
                    severity="high",
                    action="email",
                )
            )

    return BuildPlan(
        app_name=app_dir.name,
        app_description="Monitors pod restart spikes for the payments namespace and alerts on restart storms.",
        data_source=DataSource(
            sourcetype="kubernetes:events",
            parsing_strategy="json",
            fields_extracted=[
                FieldExtraction(name="pod_name", type="string", extraction="regex"),
                FieldExtraction(name="namespace", type="string", extraction="regex"),
                FieldExtraction(name="event_type", type="string", extraction="regex"),
                FieldExtraction(name="restart_count", type="number", extraction="regex"),
                FieldExtraction(name="timestamp", type="string", extraction="regex"),
            ],
            input_path="/var/log/heron/k8s_events.json",
        ),
        saved_searches=saved_searches,
        dashboards=[],
        alerts=alerts,
        notes="Reconstructed from the deployed app's savedsearches.conf for the full-loop integration test.",
    )


def _poll_alert_threshold(splunk: SplunkClient, app_name: str, alert_name: str, expected: str) -> str | None:
    current = None
    for attempt in range(THRESHOLD_POLL_ATTEMPTS):
        alerts = {alert["name"]: alert for alert in splunk.list_alerts(app_name)}
        current = alerts.get(alert_name, {}).get("alert_threshold")
        if current == expected:
            return current
        if attempt < THRESHOLD_POLL_ATTEMPTS - 1:
            time.sleep(THRESHOLD_POLL_DELAY_SECONDS)
    return current


async def main() -> None:
    print("wiping local state (heron.db, synthetic data file)...")
    if DEFAULT_DB_PATH.exists():
        DEFAULT_DB_PATH.unlink()
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text("", encoding="utf-8")

    db = DBClient()
    await db.init_schema()

    splunk = SplunkClient()
    mcp = SplunkMCPClient()
    deployer = Deployer(mcp_client=mcp, splunk_client=splunk)
    approver = Approver(deployer, mcp, db)

    print(f"running synthetic data generator (noisy mode) for {NOISY_DURATION_MINUTES} minutes...")
    subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), "--mode", "noisy", "--duration", str(NOISY_DURATION_MINUTES)],
        check=True,
    )
    print(f"generator finished, waiting {INDEXING_BUFFER_SECONDS}s for indexing to catch up...")
    await asyncio.sleep(INDEXING_BUFFER_SECONDS)

    print("\nvalidating existing deployment...")
    plan = _reconstruct_plan(APP_DIR)
    PLAN_PATH.write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    validation = validate_deployment(splunk, plan)
    print(json.dumps(validation.model_dump(), indent=2))
    assert validation.passed, "expected existing deployment to pass validation"

    print("\nsnapshotting version 1 (initial deployment)...")
    version_1 = await db.snapshot_app_version(APP_NAME, _read_app_files(APP_DIR), "initial deployment")
    assert version_1 == 1, f"expected version 1, got {version_1}"
    original_savedsearches = _read_app_files(APP_DIR)[SAVEDSEARCHES_CONF]

    print("\nobserving app...")
    observer = Observer(splunk)
    observation = await observer.observe_app(APP_NAME)
    print(json.dumps(observation.model_dump(mode="json"), indent=2))
    await db.store_observation(observation)

    print("\nrunning tuner...")
    tuner = Tuner(genai.Client(api_key=os.environ["GEMINI_API_KEY"]))
    proposals = await tuner.propose_changes(APP_NAME, observation)
    for proposal in proposals:
        print(json.dumps(proposal.model_dump(mode="json"), indent=2))
        await db.store_proposal(proposal)

    raise_proposals = [
        p
        for p in proposals
        if p.change_type == "alert_threshold" and float(p.proposed_value) > float(p.current_value)
    ]
    assert raise_proposals, "expected at least one alert-threshold raise proposal"
    proposal = raise_proposals[0]

    print("\nrouting proposal...")
    decision = await approver.route(proposal)
    print(decision.model_dump())
    assert decision.action == "auto_apply", f"expected auto_apply, got {decision.action}"

    print("\napplying proposal...")
    apply_result = await approver.apply(proposal)
    print(apply_result.model_dump())
    assert apply_result.success, f"apply failed: {apply_result.error}"
    assert apply_result.before_version == 2, f"expected before_version 2, got {apply_result.before_version}"
    assert apply_result.after_version == 3, f"expected after_version 3, got {apply_result.after_version}"

    print("\nverifying new threshold in splunk...")
    new_threshold = _format_conf_number(proposal.proposed_value)
    live_threshold = _poll_alert_threshold(splunk, APP_NAME, proposal.target["alert_name"], new_threshold)
    assert live_threshold == new_threshold, f"expected live threshold {new_threshold}, got {live_threshold}"

    print("\nchecking changelog...")
    changelog = await db.list_changelog(APP_NAME)
    assert changelog, "expected at least one changelog entry"
    print(changelog[0]["message"])
    assert "Auto-tuned alert" in changelog[0]["message"]

    print("\nrolling back to version 1...")
    rollback_result = await approver.rollback(APP_NAME, 1)
    print(rollback_result.model_dump())
    assert rollback_result.success, f"rollback failed: {rollback_result.error}"

    print("\nverifying threshold restored in splunk...")
    restored_threshold = _poll_alert_threshold(splunk, APP_NAME, proposal.target["alert_name"], "5")
    assert restored_threshold == "5", f"expected restored threshold 5, got {restored_threshold}"

    restored_savedsearches = _read_app_files(APP_DIR)[SAVEDSEARCHES_CONF]
    assert restored_savedsearches == original_savedsearches, "savedsearches.conf not bit-exact after rollback"

    rollback_changelog = await db.list_changelog(APP_NAME)
    print(rollback_changelog[0]["message"])
    assert "Rolled back" in rollback_changelog[0]["message"]

    print("\nfull loop completed successfully")


if __name__ == "__main__":
    asyncio.run(main())

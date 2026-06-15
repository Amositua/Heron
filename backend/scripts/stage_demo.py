"""Stages a reproducible demo state for Heron.

Runs the K8s pod-monitoring genesis flow (Planner -> Builder -> Deployer), drives
the synthetic data generator until the maintenance loop auto-tunes the alert
threshold, then backdates the relevant timestamps so the demo opens on a
"two weeks later" changelog entry.
"""

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiosqlite
from google import genai

from heron.approver.approver import APP_ROOT, Approver, _read_app_files
from heron.builder.builder import Builder
from heron.deployer.deployer import Deployer
from heron.observer.observer import Observer
from heron.planner.planner import Planner
from heron.splunk.mcp_client import SplunkMCPClient
from heron.splunk.splunk_client import SplunkClient
from heron.storage.db import DEFAULT_DB_PATH, DBClient
from heron.tuner.tuner import Tuner

K8S_PROMPT = (
    "I need to monitor pod restart spikes in our payments namespace. "
    "Alert me when there are more than 5 restarts in 10 minutes for any pod in that namespace."
)

DATA_FILE = Path("/var/log/heron/k8s_events.json")
GENERATOR_SCRIPT = Path(__file__).resolve().parent / "generate_k8s_data.py"
NOISY_DURATION_MINUTES = 3
INDEXING_BUFFER_SECONDS = 10

DEPLOYED_AGO = timedelta(days=14)
TUNED_AGO = timedelta(days=10)


async def _backdate(app_name: str, deploy_version: int, before_version: int, after_version: int) -> None:
    deployed_at = (datetime.now(timezone.utc) - DEPLOYED_AGO).isoformat()
    tuned_before = (datetime.now(timezone.utc) - TUNED_AGO).isoformat()
    tuned_after = (datetime.now(timezone.utc) - TUNED_AGO + timedelta(minutes=1)).isoformat()

    async with aiosqlite.connect(DEFAULT_DB_PATH) as db:
        await db.execute(
            "UPDATE app_versions SET created_at = ? WHERE app_name = ? AND version = ?",
            (deployed_at, app_name, deploy_version),
        )
        await db.execute(
            "UPDATE app_versions SET created_at = ? WHERE app_name = ? AND version = ?",
            (tuned_before, app_name, before_version),
        )
        await db.execute(
            "UPDATE app_versions SET created_at = ? WHERE app_name = ? AND version = ?",
            (tuned_after, app_name, after_version),
        )
        await db.execute(
            """UPDATE applied_changes SET applied_at = ?
               WHERE app_name = ? AND before_version = ? AND after_version = ?""",
            (tuned_after, app_name, before_version, after_version),
        )
        await db.commit()


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

    print("\nplanning k8s pod-monitoring app...")
    planner = Planner()
    plan = await planner.plan(K8S_PROMPT)
    print(f"app_name: {plan.app_name}")

    print("removing any existing deployment of this app...")
    try:
        await mcp.uninstall_app(plan.app_name)
    except Exception:
        pass

    print("\nbuilding and deploying app...")
    builder = Builder()
    result = builder.build(plan, str(APP_ROOT))
    app_dir = Path(result.app_path)
    (APP_ROOT / f"{plan.app_name}.plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")

    deploy_result = await deployer.deploy(result.app_path, plan)
    if not deploy_result.success:
        raise RuntimeError(f"deployment failed: {deploy_result.error}")

    print("\nsnapshotting version 1 (initial deployment)...")
    version_1 = await db.snapshot_app_version(plan.app_name, _read_app_files(app_dir), "initial deployment")

    print(f"\nrunning synthetic data generator (noisy mode) for {NOISY_DURATION_MINUTES} minutes...")
    subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), "--mode", "noisy", "--duration", str(NOISY_DURATION_MINUTES)],
        check=True,
    )
    print(f"generator finished, waiting {INDEXING_BUFFER_SECONDS}s for indexing to catch up...")
    await asyncio.sleep(INDEXING_BUFFER_SECONDS)

    print("\nobserving app...")
    observer = Observer(splunk)
    observation = await observer.observe_app(plan.app_name)
    await db.store_observation(observation)

    print("\nrunning tuner...")
    tuner = Tuner(genai.Client(api_key=os.environ["GEMINI_API_KEY"]))
    proposals = await tuner.propose_changes(plan.app_name, observation)
    for proposal in proposals:
        await db.store_proposal(proposal)

    raise_proposals = [
        p
        for p in proposals
        if p.change_type == "alert_threshold" and float(p.proposed_value) > float(p.current_value)
    ]
    if not raise_proposals:
        raise RuntimeError("tuner did not propose an alert-threshold raise")
    proposal = raise_proposals[0]

    print("\nrouting and applying auto-tune proposal...")
    decision = await approver.route(proposal)
    if decision.action != "auto_apply":
        raise RuntimeError(f"expected auto_apply, got {decision.action}")

    apply_result = await approver.apply(proposal)
    if not apply_result.success:
        raise RuntimeError(f"apply failed: {apply_result.error}")

    print("\nbackdating timestamps for the 'two weeks later' demo framing...")
    await _backdate(plan.app_name, version_1, apply_result.before_version, apply_result.after_version)

    print("\ndemo state ready:")
    print(f"  app: {plan.app_name}")
    print(f"  deployed (v{version_1}): {DEPLOYED_AGO.days} days ago")
    print(
        f"  auto-tuned (v{apply_result.before_version} -> v{apply_result.after_version}): "
        f"{TUNED_AGO.days} days ago"
    )
    print(f"  changelog: {apply_result.changelog_message}")


if __name__ == "__main__":
    asyncio.run(main())

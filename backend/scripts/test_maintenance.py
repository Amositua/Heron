import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from google import genai

from heron.observer.observer import Observer
from heron.splunk.splunk_client import SplunkClient
from heron.storage.db import DBClient
from heron.tuner.tuner import Tuner

APP_NAME = "payments_pod_monitoring"
GENERATOR_SCRIPT = Path(__file__).resolve().parent / "generate_k8s_data.py"
NOISY_DURATION_MINUTES = 2
INDEXING_BUFFER_SECONDS = 10


async def main() -> None:
    print(f"running synthetic data generator (noisy mode) for {NOISY_DURATION_MINUTES} minutes...")
    subprocess.run(
        [sys.executable, str(GENERATOR_SCRIPT), "--mode", "noisy", "--duration", str(NOISY_DURATION_MINUTES)],
        check=True,
    )

    print(f"generator finished, waiting {INDEXING_BUFFER_SECONDS}s for indexing to catch up...")
    await asyncio.sleep(INDEXING_BUFFER_SECONDS)

    observer = Observer(SplunkClient())
    report = await observer.observe_app(APP_NAME)
    print("\nobservation report:")
    print(json.dumps(report.model_dump(mode="json"), indent=2))

    db = DBClient()
    await db.init_schema()
    await db.store_observation(report)

    tuner = Tuner(genai.Client(api_key=os.environ["GEMINI_API_KEY"]))
    proposals = await tuner.propose_changes(APP_NAME, report)

    print(f"\n{len(proposals)} proposal(s):")
    for proposal in proposals:
        print(json.dumps(proposal.model_dump(mode="json"), indent=2))
        await db.store_proposal(proposal)

    raise_proposals = [
        p
        for p in proposals
        if p.change_type == "alert_threshold" and float(p.proposed_value) > float(p.current_value)
    ]
    assert raise_proposals, "expected at least one alert-threshold raise proposal"

    print("\nraise-threshold proposal rationale:")
    print(raise_proposals[0].rationale)


if __name__ == "__main__":
    asyncio.run(main())

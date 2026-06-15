import asyncio
import json
from pathlib import Path

from heron.builder.builder import Builder
from heron.planner.planner import Planner

K8S_PROMPT = (
    "I need to monitor pod restart spikes in our payments namespace. "
    "Alert me when there are more than 5 restarts in 10 minutes for any pod in that namespace."
)

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "splunk-app"


async def main() -> None:
    planner = Planner()
    plan = await planner.plan(K8S_PROMPT)

    builder = Builder()
    result = builder.build(plan, str(OUTPUT_ROOT))

    print(json.dumps(result.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())

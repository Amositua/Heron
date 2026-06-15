import asyncio
import json

from heron.planner.planner import Planner

K8S_PROMPT = (
    "I need to monitor pod restart spikes in our payments namespace. "
    "Alert me when there are more than 5 restarts in 10 minutes for any pod in that namespace."
)


async def main() -> None:
    planner = Planner()
    plan = await planner.plan(K8S_PROMPT)
    print(json.dumps(plan.model_dump(), indent=2))


if __name__ == "__main__":
    asyncio.run(main())

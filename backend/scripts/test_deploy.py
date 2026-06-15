import asyncio
import json
import subprocess
import sys
from pathlib import Path

from heron.builder.builder import Builder
from heron.deployer.deployer import Deployer
from heron.planner.planner import Planner

K8S_PROMPT = (
    "I need to monitor pod restart spikes in our payments namespace. "
    "Alert me when there are more than 5 restarts in 10 minutes for any pod in that namespace."
)

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "splunk-app"
GENERATOR_SCRIPT = Path(__file__).resolve().parent / "generate_k8s_data.py"


async def main() -> None:
    generator = subprocess.Popen(
        [sys.executable, str(GENERATOR_SCRIPT), "--mode", "normal", "--duration", "2"]
    )
    try:
        print("started synthetic data generator (normal mode), waiting 30s for data to flow...")
        await asyncio.sleep(30)

        planner = Planner()
        plan = await planner.plan(K8S_PROMPT)

        builder = Builder()
        build_result = builder.build(plan, str(OUTPUT_ROOT))
        print(f"built app at {build_result.app_path}")

        deployer = Deployer()
        deploy_result = await deployer.deploy(build_result.app_path, plan)

        print(json.dumps(deploy_result.model_dump(), indent=2))
        assert deploy_result.success, f"deployment failed: {deploy_result.error}"
        assert deploy_result.validation is not None and deploy_result.validation.passed
        print("deploy succeeded and validation passed")
    finally:
        generator.terminate()
        generator.wait()


if __name__ == "__main__":
    asyncio.run(main())

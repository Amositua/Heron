from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from heron.builder.builder import Builder
from heron.deployer.deployer import Deployer
from heron.models.build_plan import BuildPlan
from heron.models.build_result import BuildResult
from heron.models.deploy_result import DeployResult
from heron.planner.planner import Planner, PlannerError

SPLUNK_APP_OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "splunk-app"

app = FastAPI(title="Heron")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "heron"}


class PlanRequest(BaseModel):
    prompt: str


@app.post("/api/plan")
async def create_plan(request: PlanRequest) -> BuildPlan:
    planner = Planner()
    try:
        return await planner.plan(request.prompt)
    except PlannerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/build")
async def create_build(plan: BuildPlan) -> BuildResult:
    builder = Builder()
    result = builder.build(plan, str(SPLUNK_APP_OUTPUT_ROOT))
    _plan_path(result.app_path).write_text(plan.model_dump_json(indent=2), encoding="utf-8")
    return result


class DeployRequest(BaseModel):
    app_path: str


@app.post("/api/deploy")
async def create_deploy(request: DeployRequest) -> DeployResult:
    plan_path = _plan_path(request.app_path)
    if not plan_path.exists():
        raise HTTPException(status_code=404, detail=f"no build plan found for app at {request.app_path}")

    plan = BuildPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))

    deployer = Deployer()
    return await deployer.deploy(request.app_path, plan)


def _plan_path(app_path: str) -> Path:
    app_dir = Path(app_path)
    return app_dir.parent / f"{app_dir.name}.plan.json"

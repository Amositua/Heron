import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from google import genai
from pydantic import BaseModel

from heron.builder.builder import Builder
from heron.deployer.deployer import Deployer
from heron.models.build_plan import BuildPlan
from heron.models.build_result import BuildResult
from heron.models.deploy_result import DeployResult
from heron.models.observation import ObservationReport
from heron.models.proposal import Proposal
from heron.observer.observer import Observer
from heron.planner.planner import Planner, PlannerError
from heron.splunk.splunk_client import SplunkClient
from heron.storage.db import DBClient
from heron.tuner.tuner import Tuner, TunerError

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


def _gemini_client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


@app.get("/api/observe/{app_name}")
async def get_observation(app_name: str) -> ObservationReport:
    db = DBClient()
    await db.init_schema()

    observer = Observer(SplunkClient())
    report = await observer.observe_app(app_name)
    await db.store_observation(report)
    return report


@app.get("/api/proposals")
async def get_proposals(app_name: str | None = None, status: str = "pending") -> list[Proposal]:
    if status != "pending":
        raise HTTPException(status_code=400, detail="only status=pending is supported in v1")

    db = DBClient()
    await db.init_schema()
    return await db.list_pending_proposals(app_name)


class ObserveRunRequest(BaseModel):
    app_name: str


class ObserveRunResult(BaseModel):
    report: ObservationReport
    proposals: list[Proposal]


@app.post("/api/observe/run")
async def trigger_observe_run(request: ObserveRunRequest) -> ObserveRunResult:
    db = DBClient()
    await db.init_schema()

    observer = Observer(SplunkClient())
    report = await observer.observe_app(request.app_name)
    await db.store_observation(report)

    tuner = Tuner(_gemini_client())
    try:
        proposals = await tuner.propose_changes(request.app_name, report)
    except TunerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    for proposal in proposals:
        await db.store_proposal(proposal)

    return ObserveRunResult(report=report, proposals=proposals)

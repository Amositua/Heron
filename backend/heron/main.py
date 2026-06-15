from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from heron.builder.builder import Builder
from heron.models.build_plan import BuildPlan
from heron.models.build_result import BuildResult
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
    return builder.build(plan, str(SPLUNK_APP_OUTPUT_ROOT))

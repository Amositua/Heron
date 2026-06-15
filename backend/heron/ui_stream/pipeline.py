import asyncio
import logging
from pathlib import Path

from heron.builder.builder import Builder
from heron.deployer.deployer import Deployer
from heron.planner.planner import Planner, PlannerError
from heron.ui_stream.bus import bus
from heron.ui_stream.events import BuildEvent, EventType

logger = logging.getLogger(__name__)

STREAM_STEP_DELAY_SECONDS = 0.4


async def run_genesis(build_id: str, prompt: str, output_root: Path) -> None:
    """Runs Planner -> Builder -> Deployer, publishing progress events for the build view."""
    try:
        await _emit(build_id, "stage_change", {"stage": "planning"})

        planner = Planner()
        try:
            plan = await planner.plan(prompt)
        except PlannerError as exc:
            await _emit(build_id, "error", {"message": str(exc)})
            return

        await _emit(
            build_id,
            "file_written",
            {"filename": "build_plan.json", "content": plan.model_dump_json(indent=2)},
        )

        await _emit(build_id, "stage_change", {"stage": "generating"})

        builder = Builder()
        result = builder.build(plan, str(output_root))
        _plan_path(result.app_path).write_text(plan.model_dump_json(indent=2), encoding="utf-8")

        for file_path_str in result.files_created:
            file_path = Path(file_path_str)
            content = file_path.read_text(encoding="utf-8")
            await _emit(
                build_id,
                "file_written",
                {"filename": file_path.relative_to(result.app_path).as_posix(), "content": content},
            )
            await asyncio.sleep(STREAM_STEP_DELAY_SECONDS)

        await _emit(build_id, "stage_change", {"stage": "deploying"})

        deployer = Deployer()
        deploy_result = await deployer.deploy(result.app_path, plan)

        for action in deploy_result.actions:
            await _emit(build_id, "mcp_action", {"action": action, "target": deploy_result.app_name})
            await asyncio.sleep(STREAM_STEP_DELAY_SECONDS)

        await _emit(build_id, "stage_change", {"stage": "validating"})

        if deploy_result.validation is not None:
            for check in deploy_result.validation.checks:
                await _emit(
                    build_id,
                    "validation_step",
                    {"name": check.name, "passed": check.passed, "detail": check.detail},
                )
                await asyncio.sleep(STREAM_STEP_DELAY_SECONDS)

        if not deploy_result.success:
            await _emit(build_id, "error", {"message": deploy_result.error or "deployment failed"})
            return

        await _emit(build_id, "stage_change", {"stage": "done"})
        await _emit(
            build_id,
            "complete",
            {"app_name": deploy_result.app_name, "app_path": deploy_result.app_path},
        )
    except Exception as exc:
        logger.exception("genesis pipeline failed", extra={"build_id": build_id})
        await _emit(build_id, "error", {"message": str(exc)})


async def _emit(build_id: str, event_type: EventType, data: dict) -> None:
    await bus.publish(build_id, BuildEvent(type=event_type, data=data))


def _plan_path(app_path: str) -> Path:
    app_dir = Path(app_path)
    return app_dir.parent / f"{app_dir.name}.plan.json"

import asyncio
import logging
import tarfile
import uuid
from pathlib import Path

from heron.deployer.validators import validate_deployment
from heron.models.build_plan import BuildPlan
from heron.models.deploy_result import DeployResult
from heron.splunk.mcp_client import MCPError, SplunkMCPClient
from heron.splunk.splunk_client import SplunkClient

logger = logging.getLogger(__name__)

STAGING_DIR = Path("/var/log/heron/staging")
POST_INSTALL_WAIT_SECONDS = 10


class Deployer:
    """Packages a generated Splunk app, installs it via MCP, and validates it.

    On validation failure the app is uninstalled (rolled back) via MCP so
    the Splunk instance is never left in a half-deployed state.
    """

    def __init__(
        self,
        mcp_client: SplunkMCPClient | None = None,
        splunk_client: SplunkClient | None = None,
    ) -> None:
        self._mcp = mcp_client or SplunkMCPClient()
        self._splunk = splunk_client or SplunkClient()

    async def deploy(self, app_path: str, plan: BuildPlan) -> DeployResult:
        app_dir = Path(app_path)
        actions: list[str] = []

        tarball_path = _create_tarball(app_dir)
        logger.info("packaged app for deploy", extra={"app_name": plan.app_name, "tarball": str(tarball_path)})

        try:
            await self._mcp.install_app(str(tarball_path))
            actions.append("install_app")
        except MCPError as exc:
            logger.error("install_app failed", extra={"app_name": plan.app_name, "error": str(exc)})
            return DeployResult(
                success=False,
                app_name=plan.app_name,
                app_path=str(app_dir),
                actions=actions,
                error=f"install failed: {exc}",
            )

        await asyncio.sleep(POST_INSTALL_WAIT_SECONDS)

        report = validate_deployment(self._splunk, plan)

        if report.passed:
            return DeployResult(
                success=True,
                app_name=plan.app_name,
                app_path=str(app_dir),
                actions=actions,
                validation=report,
            )

        error_parts = ["post-deploy validation failed"]
        try:
            await self._mcp.uninstall_app(plan.app_name)
            actions.append("uninstall_app")
            rolled_back = True
        except MCPError as exc:
            logger.error("rollback uninstall_app failed", extra={"app_name": plan.app_name, "error": str(exc)})
            rolled_back = False
            error_parts.append(f"rollback failed: {exc}")

        return DeployResult(
            success=False,
            app_name=plan.app_name,
            app_path=str(app_dir),
            actions=actions,
            validation=report,
            rolled_back=rolled_back,
            error="; ".join(error_parts),
        )


def _create_tarball(app_dir: Path) -> Path:
    staging_dir = STAGING_DIR.resolve()
    staging_dir.mkdir(parents=True, exist_ok=True)
    tarball_path = staging_dir / f"{app_dir.name}-{uuid.uuid4().hex[:8]}.tar.gz"
    with tarfile.open(tarball_path, "w:gz") as tar:
        tar.add(app_dir, arcname=app_dir.name)
    return tarball_path

import configparser
import io
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from heron.deployer.deployer import Deployer
from heron.models.approval import ApplyResult, RollbackResult, RoutingDecision
from heron.models.build_plan import BuildPlan
from heron.models.proposal import Proposal
from heron.splunk.mcp_client import MCPError, SplunkMCPClient
from heron.storage.db import DBClient

logger = logging.getLogger(__name__)

APP_ROOT = Path(__file__).resolve().parents[3] / "splunk-app"
SAVEDSEARCHES_CONF = "default/savedsearches.conf"

DEFAULT_AUTO_APPLY_MEDIUM_RISK_APPS = {"payments_pod_monitoring"}

FIELD_TO_CONF_KEY = {"alert_threshold": "quantity"}


class Approver:
    """Routes Tuner proposals, applies approved changes via MCP, and tracks versions."""

    def __init__(
        self,
        deployer: Deployer,
        mcp_client: SplunkMCPClient,
        db_client: DBClient,
        app_root: Path | None = None,
        auto_apply_medium_risk_apps: set[str] | None = None,
    ) -> None:
        self._deployer = deployer
        self._mcp = mcp_client
        self._db = db_client
        self._app_root = app_root or APP_ROOT
        self._auto_apply_medium_risk_apps = (
            DEFAULT_AUTO_APPLY_MEDIUM_RISK_APPS
            if auto_apply_medium_risk_apps is None
            else auto_apply_medium_risk_apps
        )

    async def route(self, proposal: Proposal) -> RoutingDecision:
        if proposal.risk_level == "low":
            return RoutingDecision(
                proposal_id=proposal.id, action="auto_apply", reason="low-risk changes apply automatically"
            )

        if proposal.risk_level == "medium" and proposal.app_name in self._auto_apply_medium_risk_apps:
            return RoutingDecision(
                proposal_id=proposal.id,
                action="auto_apply",
                reason=f"medium-risk alert tuning is auto-applied for {proposal.app_name}",
            )

        if proposal.risk_level == "medium":
            reason = "medium-risk changes require human review by default"
        else:
            reason = "high-risk changes always require human review"
        return RoutingDecision(proposal_id=proposal.id, action="queue_for_review", reason=reason)

    async def apply(self, proposal: Proposal) -> ApplyResult:
        if proposal.change_type != "alert_threshold":
            logger.info("apply not implemented for v1", extra={"change_type": proposal.change_type})
            return ApplyResult(
                success=False,
                proposal_id=proposal.id,
                app_name=proposal.app_name,
                error=f"applying '{proposal.change_type}' changes is not implemented for v1",
            )

        app_dir = self._app_root / proposal.app_name
        stanza = proposal.target["alert_name"]
        conf_key = FIELD_TO_CONF_KEY[proposal.target["field"]]
        new_value = _format_conf_number(proposal.proposed_value)

        before_snapshot = _read_app_files(app_dir)
        before_version = await self._db.snapshot_app_version(
            proposal.app_name, before_snapshot, f"before applying proposal {proposal.id}"
        )

        updated_conf = _update_conf_value(before_snapshot[SAVEDSEARCHES_CONF], stanza, conf_key, new_value)
        (app_dir / SAVEDSEARCHES_CONF).write_text(updated_conf, encoding="utf-8")

        try:
            await self._mcp.update_app_config(proposal.app_name, "savedsearches", stanza, quantity=new_value)
        except MCPError as exc:
            (app_dir / SAVEDSEARCHES_CONF).write_text(before_snapshot[SAVEDSEARCHES_CONF], encoding="utf-8")
            return ApplyResult(success=False, proposal_id=proposal.id, app_name=proposal.app_name, error=str(exc))

        after_snapshot = _read_app_files(app_dir)
        after_version = await self._db.snapshot_app_version(
            proposal.app_name, after_snapshot, f"after applying proposal {proposal.id}"
        )

        display_name = _alert_display_name(self._app_root, proposal.app_name, stanza)
        message = _format_changelog_message(display_name, proposal)

        await self._db.store_applied_change(
            proposal_id=proposal.id,
            app_name=proposal.app_name,
            change_type=proposal.change_type,
            target=proposal.target,
            previous_value=proposal.current_value,
            new_value=proposal.proposed_value,
            message=message,
            before_version=before_version,
            after_version=after_version,
        )
        await self._db.update_proposal_status(proposal.id, "applied")

        return ApplyResult(
            success=True,
            proposal_id=proposal.id,
            app_name=proposal.app_name,
            before_version=before_version,
            after_version=after_version,
            changelog_message=message,
        )

    async def reject(self, proposal_id: str, reason: str) -> None:
        await self._db.update_proposal_status(proposal_id, "rejected")
        logger.info("proposal rejected", extra={"proposal_id": proposal_id, "reason": reason})

    async def rollback(self, app_name: str, target_version_id: int) -> RollbackResult:
        target = await self._db.get_version(app_name, target_version_id)
        if target is None:
            return RollbackResult(success=False, app_name=app_name, error=f"version {target_version_id} not found")

        app_dir = self._app_root / app_name
        target_snapshot = target["snapshot"]
        current_snapshot = _read_app_files(app_dir)

        before_version = await self._db.snapshot_app_version(
            app_name, current_snapshot, f"before rollback to version {target_version_id}"
        )

        for stanza, quantity in _diff_quantities(
            current_snapshot.get(SAVEDSEARCHES_CONF, ""), target_snapshot.get(SAVEDSEARCHES_CONF, "")
        ):
            await self._mcp.update_app_config(app_name, "savedsearches", stanza, quantity=quantity)

        _write_app_files(app_dir, target_snapshot)

        after_version = await self._db.snapshot_app_version(
            app_name, _read_app_files(app_dir), f"rolled back to version {target_version_id}"
        )

        message = f"[{_now_str()}] Rolled back '{app_name}' to version {target_version_id}."
        await self._db.store_applied_change(
            proposal_id=None,
            app_name=app_name,
            change_type="rollback",
            target={"target_version": target_version_id},
            previous_value=before_version,
            new_value=target_version_id,
            message=message,
            before_version=before_version,
            after_version=after_version,
        )

        return RollbackResult(
            success=True,
            app_name=app_name,
            restored_version=target_version_id,
            new_version=after_version,
            changelog_message=message,
        )


def _read_app_files(app_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(app_dir.rglob("*")):
        if path.is_file():
            files[path.relative_to(app_dir).as_posix()] = path.read_text(encoding="utf-8")
    return files


def _write_app_files(app_dir: Path, snapshot: dict[str, str]) -> None:
    for rel_path, content in snapshot.items():
        path = app_dir / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _update_conf_value(content: str, stanza: str, key: str, value: str) -> str:
    parser = configparser.ConfigParser(strict=False, interpolation=None)
    parser.optionxform = str
    parser.read_string(content)
    parser.set(stanza, key, value)
    buf = io.StringIO()
    parser.write(buf)
    return buf.getvalue()


def _diff_quantities(old_content: str, new_content: str) -> list[tuple[str, str]]:
    if not old_content or not new_content:
        return []

    old_parser = configparser.ConfigParser(strict=False, interpolation=None)
    old_parser.optionxform = str
    old_parser.read_string(old_content)

    new_parser = configparser.ConfigParser(strict=False, interpolation=None)
    new_parser.optionxform = str
    new_parser.read_string(new_content)

    changes: list[tuple[str, str]] = []
    for stanza in new_parser.sections():
        if not new_parser.has_option(stanza, "quantity"):
            continue
        new_quantity = new_parser.get(stanza, "quantity")
        old_quantity = old_parser.get(stanza, "quantity", fallback=None)
        if new_quantity != old_quantity:
            changes.append((stanza, new_quantity))
    return changes


def _alert_display_name(app_root: Path, app_name: str, search_name: str) -> str:
    plan_path = app_root / f"{app_name}.plan.json"
    if not plan_path.exists():
        return search_name

    try:
        plan = BuildPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    except Exception:
        return search_name

    for alert in plan.alerts:
        if alert.search_name == search_name:
            return alert.name
    return search_name


def _format_conf_number(value: Any) -> str:
    number = float(value)
    if number == int(number):
        return str(int(number))
    return str(number)


def _format_changelog_message(display_name: str, proposal: Proposal) -> str:
    timestamp = proposal.created_at.strftime("%Y-%m-%d %H:%M")
    current = _format_conf_number(proposal.current_value)
    proposed = _format_conf_number(proposal.proposed_value)
    return (
        f"[{timestamp}] Auto-tuned alert '{display_name}': threshold {current} -> {proposed}. "
        f"Reason: {proposal.rationale}"
    )


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")

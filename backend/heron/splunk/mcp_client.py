import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / ".env", override=True)

logger = logging.getLogger(__name__)

AUDIT_LOG_PATH = Path(__file__).resolve().parents[2] / "logs" / "mcp_audit.log"

TIMEOUT_SECONDS = 10.0
MAX_RETRIES = 3


class MCPError(Exception):
    """Raised when an MCP tool call fails after all retries."""


class SplunkMCPClient:
    """Client for Splunk MCP Server tool calls.

    Every write Heron makes to Splunk goes through this client so it is
    captured in the MCP server's tool registry and mirrored to a local
    structured audit log.
    """

    def __init__(self, mcp_url: str | None = None, token: str | None = None) -> None:
        self._mcp_url = mcp_url or os.environ["SPLUNK_MCP_URL"]
        self._token = token or os.environ["SPLUNK_MCP_TOKEN"]
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    async def install_app(self, app_path: str) -> dict[str, Any]:
        return await self._call_tool(
            "heron_install_app", {"app_path": app_path}, action="install_app", target=app_path
        )

    async def uninstall_app(self, app_name: str) -> dict[str, Any]:
        return await self._call_tool(
            "heron_uninstall_app", {"app_name": app_name}, action="uninstall_app", target=app_name
        )

    async def restart_splunkd(self) -> dict[str, Any]:
        return await self._call_tool(
            "heron_restart_splunkd", {}, action="restart_splunkd", target="splunkd"
        )

    async def update_app_config(
        self,
        app_name: str,
        conf_file: str,
        stanza: str,
        quantity: str | int | None = None,
        earliest_time: str | None = None,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"app_name": app_name, "conf_file": conf_file, "stanza": stanza}
        if quantity is not None:
            arguments["quantity"] = str(quantity)
        if earliest_time is not None:
            arguments["earliest_time"] = earliest_time
        target = f"{app_name}/{conf_file}/{stanza}"
        return await self._call_tool(
            "heron_update_app_config", arguments, action="update_app_config", target=target
        )

    async def list_apps(self) -> dict[str, Any]:
        return await self._call_tool("heron_list_apps", {}, action="list_apps", target="apps/local")

    async def _call_tool(
        self, tool_name: str, arguments: dict[str, Any], *, action: str, target: str
    ) -> dict[str, Any]:
        payload = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        }
        headers = {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

        last_error: Exception | None = None
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, verify=False) as client:
                    response = await client.post(self._mcp_url, json=payload, headers=headers)
                response.raise_for_status()
                body = response.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt < MAX_RETRIES:
                    logger.warning(
                        "MCP tool '%s' attempt %d/%d failed: %s", tool_name, attempt, MAX_RETRIES, exc
                    )
                    await asyncio.sleep(2 ** (attempt - 1))
                    continue
                self._audit(action, target, "failure", attempts=attempt, error=str(exc))
                raise MCPError(
                    f"MCP tool '{tool_name}' unreachable after {MAX_RETRIES} attempts: {exc}"
                ) from exc
        else:
            raise MCPError(f"MCP tool '{tool_name}' failed: {last_error}") from last_error

        if "error" in body:
            self._audit(action, target, "failure", attempts=attempt, error=str(body["error"]))
            raise MCPError(f"MCP tool '{tool_name}' returned an error: {body['error']}")

        self._audit(action, target, "success", attempts=attempt)
        return body.get("result", {})

    def _audit(self, action: str, target: str, outcome: str, *, attempts: int, error: str | None = None) -> None:
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "target": target,
            "outcome": outcome,
            "attempts": attempts,
        }
        if error is not None:
            entry["error"] = error

        logger.info("mcp_audit", extra={"audit": entry})
        with open(AUDIT_LOG_PATH, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

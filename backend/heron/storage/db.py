import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from heron.models.observation import ObservationReport
from heron.models.proposal import Proposal

DEFAULT_DB_PATH = Path(__file__).resolve().parents[3] / "heron.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    timestamp TEXT NOT NULL,
    report_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS proposals (
    id TEXT PRIMARY KEY,
    app_name TEXT NOT NULL,
    change_type TEXT NOT NULL,
    target_json TEXT NOT NULL,
    current_value_json TEXT NOT NULL,
    proposed_value_json TEXT NOT NULL,
    rationale TEXT NOT NULL,
    risk_level TEXT NOT NULL,
    created_at TEXT NOT NULL,
    status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS applied_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT,
    app_name TEXT NOT NULL,
    change_type TEXT NOT NULL,
    target_json TEXT NOT NULL,
    previous_value_json TEXT NOT NULL,
    new_value_json TEXT NOT NULL,
    message TEXT NOT NULL,
    before_version INTEGER NOT NULL,
    after_version INTEGER NOT NULL,
    applied_at TEXT NOT NULL,
    rolled_back INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    app_name TEXT NOT NULL,
    version INTEGER NOT NULL,
    snapshot_json TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


class DBClient:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self._db_path = str(db_path or os.environ.get("HERON_DB_PATH", DEFAULT_DB_PATH))

    async def init_schema(self) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def store_observation(self, report: ObservationReport) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "INSERT INTO observations (app_name, timestamp, report_json) VALUES (?, ?, ?)",
                (report.app_name, report.timestamp.isoformat(), report.model_dump_json()),
            )
            await db.commit()
            return cursor.lastrowid

    async def store_proposal(self, proposal: Proposal) -> str:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute(
                """INSERT INTO proposals
                   (id, app_name, change_type, target_json, current_value_json,
                    proposed_value_json, rationale, risk_level, created_at, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    proposal.id,
                    proposal.app_name,
                    proposal.change_type,
                    json.dumps(proposal.target),
                    json.dumps(proposal.current_value),
                    json.dumps(proposal.proposed_value),
                    proposal.rationale,
                    proposal.risk_level,
                    proposal.created_at.isoformat(),
                    proposal.status,
                ),
            )
            await db.commit()
            return proposal.id

    async def list_pending_proposals(self, app_name: str | None = None) -> list[Proposal]:
        query = "SELECT * FROM proposals WHERE status = 'pending'"
        params: tuple[Any, ...] = ()
        if app_name is not None:
            query += " AND app_name = ?"
            params = (app_name,)
        query += " ORDER BY created_at DESC"

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [_row_to_proposal(row) for row in rows]

    async def get_proposal(self, proposal_id: str) -> Proposal | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute("SELECT * FROM proposals WHERE id = ?", (proposal_id,))
            row = await cursor.fetchone()
            return _row_to_proposal(row) if row else None

    async def update_proposal_status(self, proposal_id: str, status: str) -> None:
        async with aiosqlite.connect(self._db_path) as db:
            await db.execute("UPDATE proposals SET status = ? WHERE id = ?", (status, proposal_id))
            await db.commit()

    async def store_applied_change(
        self,
        proposal_id: str | None,
        app_name: str,
        change_type: str,
        target: dict[str, Any],
        previous_value: Any,
        new_value: Any,
        message: str,
        before_version: int,
        after_version: int,
    ) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                """INSERT INTO applied_changes
                   (proposal_id, app_name, change_type, target_json, previous_value_json,
                    new_value_json, message, before_version, after_version, applied_at, rolled_back)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)""",
                (
                    proposal_id,
                    app_name,
                    change_type,
                    json.dumps(target),
                    json.dumps(previous_value),
                    json.dumps(new_value),
                    message,
                    before_version,
                    after_version,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
            await db.commit()
            return cursor.lastrowid

    async def snapshot_app_version(self, app_name: str, snapshot: dict[str, Any], description: str) -> int:
        async with aiosqlite.connect(self._db_path) as db:
            cursor = await db.execute(
                "SELECT COALESCE(MAX(version), 0) FROM app_versions WHERE app_name = ?", (app_name,)
            )
            row = await cursor.fetchone()
            next_version = (row[0] or 0) + 1

            await db.execute(
                """INSERT INTO app_versions (app_name, version, snapshot_json, description, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (app_name, next_version, json.dumps(snapshot), description, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
            return next_version

    async def get_version(self, app_name: str, version: int) -> dict[str, Any] | None:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM app_versions WHERE app_name = ? AND version = ?", (app_name, version)
            )
            row = await cursor.fetchone()
            return _row_to_version(row) if row else None

    async def list_versions(self, app_name: str) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM app_versions WHERE app_name = ? ORDER BY version DESC", (app_name,)
            )
            rows = await cursor.fetchall()
            return [_row_to_version(row) for row in rows]

    async def list_changelog(self, app_name: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM applied_changes"
        params: tuple[Any, ...] = ()
        if app_name is not None:
            query += " WHERE app_name = ?"
            params = (app_name,)
        query += " ORDER BY applied_at DESC"

        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
            return [
                {
                    "id": row["id"],
                    "proposal_id": row["proposal_id"],
                    "app_name": row["app_name"],
                    "change_type": row["change_type"],
                    "target": json.loads(row["target_json"]),
                    "previous_value": json.loads(row["previous_value_json"]),
                    "new_value": json.loads(row["new_value_json"]),
                    "message": row["message"],
                    "before_version": row["before_version"],
                    "after_version": row["after_version"],
                    "applied_at": row["applied_at"],
                    "rolled_back": bool(row["rolled_back"]),
                }
                for row in rows
            ]

    async def list_apps(self) -> list[dict[str, Any]]:
        async with aiosqlite.connect(self._db_path) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT app_name, MAX(version) AS current_version, MAX(created_at) AS last_changed_at
                   FROM app_versions GROUP BY app_name ORDER BY app_name"""
            )
            rows = await cursor.fetchall()
            return [
                {
                    "app_name": row["app_name"],
                    "current_version": row["current_version"],
                    "last_changed_at": row["last_changed_at"],
                }
                for row in rows
            ]


def _row_to_proposal(row: aiosqlite.Row) -> Proposal:
    return Proposal(
        id=row["id"],
        app_name=row["app_name"],
        change_type=row["change_type"],
        target=json.loads(row["target_json"]),
        current_value=json.loads(row["current_value_json"]),
        proposed_value=json.loads(row["proposed_value_json"]),
        rationale=row["rationale"],
        risk_level=row["risk_level"],
        created_at=datetime.fromisoformat(row["created_at"]),
        status=row["status"],
    )


def _row_to_version(row: aiosqlite.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "app_name": row["app_name"],
        "version": row["version"],
        "snapshot": json.loads(row["snapshot_json"]),
        "description": row["description"],
        "created_at": row["created_at"],
    }

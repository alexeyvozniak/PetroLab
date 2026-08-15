from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from petrolab.db import _utcnow, connect


@dataclass(frozen=True)
class ExchangeOrigin:
    workspace_uuid: str
    entity_kind: str
    source_key: str
    local_key: str


def ensure_exchange_identity_schema() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS exchange_workspace_identity (
                singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                workspace_uuid TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS exchange_import_map (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workspace_uuid TEXT NOT NULL,
                entity_kind TEXT NOT NULL,
                source_key TEXT NOT NULL,
                local_key TEXT NOT NULL,
                imported_at TEXT NOT NULL,
                UNIQUE(workspace_uuid, entity_kind, source_key)
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_exchange_import_local "
            "ON exchange_import_map(entity_kind, local_key)"
        )
        con.commit()


def get_exchange_workspace_uuid() -> str:
    ensure_exchange_identity_schema()
    with connect() as con:
        row = con.execute(
            "SELECT workspace_uuid FROM exchange_workspace_identity WHERE singleton=1"
        ).fetchone()
        if row:
            return str(row["workspace_uuid"])
        value = uuid4().hex
        con.execute(
            "INSERT INTO exchange_workspace_identity(singleton,workspace_uuid,created_at) VALUES(1,?,?)",
            (value, _utcnow()),
        )
        con.commit()
        return value


def lookup_import_mapping(workspace_uuid: str, entity_kind: str, source_key: str) -> str | None:
    ensure_exchange_identity_schema()
    with connect() as con:
        row = con.execute(
            """SELECT local_key FROM exchange_import_map
               WHERE workspace_uuid=? AND entity_kind=? AND source_key=?""",
            (str(workspace_uuid), str(entity_kind), str(source_key)),
        ).fetchone()
    return str(row["local_key"]) if row else None


def record_import_mapping(
    con,
    *,
    workspace_uuid: str,
    entity_kind: str,
    source_key: str,
    local_key: str,
) -> None:
    """Record a stable source-to-local identity inside the caller transaction."""
    con.execute(
        """INSERT INTO exchange_import_map(
               workspace_uuid,entity_kind,source_key,local_key,imported_at
           ) VALUES (?,?,?,?,?)
           ON CONFLICT(workspace_uuid,entity_kind,source_key)
           DO UPDATE SET local_key=excluded.local_key, imported_at=excluded.imported_at""",
        (str(workspace_uuid), str(entity_kind), str(source_key), str(local_key), _utcnow()),
    )

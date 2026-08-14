from __future__ import annotations

import sqlite3

from . import db as _db
from .storage_extensions import ensure_rock_tables


def ensure_storage() -> None:
    """Create/migrate all storage through the canonical database bootstrap."""
    # Keep the core schema in one place.  In particular, this ensures that a
    # startup through ``storage`` receives the project-membership migration
    # used by the shared global database just like a startup through ``db``.
    _db.ensure_storage()
    con = sqlite3.connect(_db.DB_PATH)
    try:
        con.execute("PRAGMA foreign_keys=ON")
        ensure_rock_tables(con)
        con.commit()
    finally:
        con.close()

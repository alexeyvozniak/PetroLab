__version__ = "0.7.0"

# Keep the established database API while replacing only the bootstrap
# storage initializer with a Windows-safe implementation that closes SQLite
# handles deterministically.
from . import db as _db
from .storage import ensure_storage as _ensure_storage

_db.ensure_storage = _ensure_storage

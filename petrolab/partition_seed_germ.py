"""Built-in, source-scoped selections from the public GERM KdD catalogue.

The source file is retained verbatim so each exact Kd, uncertainty and interval
remains inspectable.  These records are a convenience library, not a default
calibration and never overwrite user models.
"""
from __future__ import annotations

from pathlib import Path

from petrolab.partition_import import import_partition_table, read_partition_upload

GERM_BASANITE_FILE = Path(__file__).parent / "data" / "germ_kdd_basanite_2026-08-14.txt"
GERM_BASANITE_NOTE = (
    "Официальная выборка GERM KdD: 323 строк из 4 вкладов для Basanite, "
    "скачана 2026-08-14. Исходные Kd, σ и интервалы сохранены без усреднения."
)


def seed_germ_basanite_models() -> list[int]:
    """Add the bundled GERM basanite table to the global model library once."""
    table = read_partition_upload(GERM_BASANITE_FILE.read_bytes(), GERM_BASANITE_FILE.name)
    return import_partition_table(table)

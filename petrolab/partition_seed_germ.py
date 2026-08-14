"""Built-in, source-scoped selections from the public GERM KdD catalogue.

Each source file is retained verbatim so exact Kd, uncertainty and interval
statements remain inspectable.  These are convenience libraries, not default
calibrations; they never overwrite user models.
"""
from __future__ import annotations

from pathlib import Path

from petrolab.partition_import import import_partition_table, read_partition_upload

_DATA_DIR = Path(__file__).parent / "data"
GERM_SELECTIONS = {
    "Basanite": _DATA_DIR / "germ_kdd_basanite_2026-08-14.txt",
    "Phonolite": _DATA_DIR / "germ_kdd_phonolite_2026-08-14.txt",
}
GERM_BASANITE_NOTE = (
    "Официальная выборка GERM KdD: 323 строки из 4 вкладов для Basanite, "
    "скачана 2026-08-14. Исходные Kd, σ и интервалы сохранены без усреднения."
)
GERM_ALKALINE_NOTE = (
    "Встроенная GERM-библиотека: Basanite (323 строки, 4 вклада) и "
    "Phonolite (24 строки, 2 вклада), скачана 2026-08-14. "
    "Исходные Kd, σ и интервалы сохранены без усреднения."
)
GERM_BASANITE_FILE = GERM_SELECTIONS["Basanite"]


def seed_germ_selection(rock_type: str) -> list[int]:
    """Add one bundled GERM selection to the global model library once."""
    source_file = GERM_SELECTIONS[rock_type]
    table = read_partition_upload(source_file.read_bytes(), source_file.name)
    return import_partition_table(table)


def seed_germ_basanite_models() -> list[int]:
    """Backward-compatible shortcut for the built-in basanite selection."""
    return seed_germ_selection("Basanite")


def seed_germ_alkaline_models() -> list[int]:
    """Add all currently bundled alkaline selections; duplicates are skipped."""
    created: list[int] = []
    for rock_type in GERM_SELECTIONS:
        created.extend(seed_germ_selection(rock_type))
    return created

from __future__ import annotations

from petrolab.db import connect, get_analysis_record
from petrolab.services.analysis_service import save_changes_and_sync, save_changes_to_database


def _restore_type(old_value: str | None, current):
    if old_value is None:
        return None
    if isinstance(current, bool):
        return str(old_value).strip().casefold() in {"1", "true", "да", "yes"}
    if isinstance(current, int) and not isinstance(current, bool):
        try:
            return int(float(old_value))
        except ValueError:
            return old_value
    if isinstance(current, float):
        try:
            return float(old_value)
        except ValueError:
            return old_value
    return old_value


def undo_change_log_entry(change_id: int):
    """Undo one raw/local edit only if its new value is still current.

    If the original change was synced to XLSX/XLSM, the inverse uses the normal
    safe sync service too, including fingerprint/conflict checks and backup.
    """
    with connect() as con:
        row = con.execute("SELECT * FROM change_log WHERE id=?", (int(change_id),)).fetchone()
    if row is None:
        raise ValueError("Запись истории не найдена")
    if not row["analysis_id"]:
        raise ValueError("У этой записи нет analysis_id для безопасной отмены")
    record = get_analysis_record(str(row["analysis_id"]))
    column = str(row["column_name"])
    current = record["data"].get(column)
    logged_new = None if row["new_value"] is None else str(row["new_value"])
    current_text = None if current is None else str(current)
    if current_text != logged_new:
        raise ValueError(
            "Значение уже менялось после этой записи. PetroLab не будет отменять старую правку поверх более нового решения."
        )
    restored = _restore_type(row["old_value"], current)
    change = {
        "dataset_id": int(row["dataset_id"]),
        "analysis_id": str(row["analysis_id"]),
        "column_name": column,
        "old_value": current,
        "new_value": restored,
    }
    if int(row["synced_to_source"] or 0):
        return save_changes_and_sync([change])
    return save_changes_to_database([change])

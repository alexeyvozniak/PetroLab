from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.analysis_identity import source_row_fingerprint
from petrolab.db import _json_safe_record, _utcnow, connect, get_dataset, list_datasets, load_dataset_dataframe
from petrolab.mineral_assignments import attach_mineral_assignments


_SOURCE_FINGERPRINT_KEY = "__source_fingerprint__"
_FORMULA_CONTEXT_COLUMNS = {
    "Минерал", "Минерал исходного набора", "Минерал назначен вручную",
    "Комментарий переотнесения", "Переотнесено",
}


@dataclass(frozen=True)
class FormulaSaveResult:
    dataset_id: int
    method_id: str
    row_count: int
    derived_columns: tuple[str, ...]


@dataclass(frozen=True)
class FormulaStatus:
    dataset_id: int
    method_id: str = ""
    method_title: str = ""
    mineral_key: str = ""
    total_rows: int = 0
    current_rows: int = 0
    stale_rows: int = 0
    valid_rows: int = 0
    invalid_rows: int = 0
    unknown_validity_rows: int = 0
    calculated_at: str = ""

    @property
    def has_active_formula(self) -> bool:
        return bool(self.method_id)


_INTERNAL_META = {"_analysis_id", "_dataset_id", "_project_id", "_row_index", "_source_row"}


def ensure_formula_storage() -> None:
    with connect() as con:
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS formula_dataset_state (
                dataset_id INTEGER PRIMARY KEY,
                active_method_id TEXT NOT NULL,
                method_title TEXT NOT NULL DEFAULT '',
                mineral_key TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS formula_results (
                dataset_id INTEGER NOT NULL,
                analysis_id TEXT NOT NULL,
                method_id TEXT NOT NULL,
                source_updated_at TEXT NOT NULL,
                derived_json TEXT NOT NULL,
                calculated_at TEXT NOT NULL,
                PRIMARY KEY(analysis_id, method_id),
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_formula_results_dataset_method ON formula_results(dataset_id, method_id)"
        )
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS analysis_formula_state (
                analysis_id TEXT PRIMARY KEY,
                dataset_id INTEGER NOT NULL,
                active_method_id TEXT NOT NULL,
                method_title TEXT NOT NULL DEFAULT '',
                mineral_key TEXT NOT NULL DEFAULT '',
                calculated_at TEXT NOT NULL,
                FOREIGN KEY(analysis_id) REFERENCES analysis_rows(analysis_id) ON DELETE CASCADE,
                FOREIGN KEY(dataset_id) REFERENCES datasets(id) ON DELETE CASCADE
            )
            """
        )
        con.execute(
            "CREATE INDEX IF NOT EXISTS idx_analysis_formula_state_dataset ON analysis_formula_state(dataset_id)"
        )
        con.commit()


def _align_result_by_analysis_id(source: pd.DataFrame, result: pd.DataFrame) -> pd.DataFrame:
    if len(source) != len(result):
        raise ValueError("Число исходных и рассчитанных строк не совпадает")
    if "_analysis_id" not in source.columns:
        raise ValueError("Для сохранения пересчёта требуется _analysis_id")
    if "_analysis_id" not in result.columns:
        raise ValueError("Результат формулы потерял _analysis_id перед сохранением")
    source_ids = source["_analysis_id"].astype(str)
    result_ids = result["_analysis_id"].astype(str)
    if source_ids.duplicated().any() or result_ids.duplicated().any():
        raise ValueError("Повторяющиеся _analysis_id не позволяют безопасно сохранить пересчёт")
    if set(source_ids) != set(result_ids):
        raise ValueError("Набор _analysis_id результата формулы не совпадает с источником")
    aligned = result.copy()
    aligned["_analysis_id"] = result_ids
    aligned = aligned.set_index("_analysis_id", drop=False).loc[source_ids.tolist()].copy()
    aligned.index = source.index
    return aligned


def _formula_source_fingerprint(record: dict) -> str:
    """Ignore local interpretation labels when checking source-chemistry freshness."""
    source_like = {
        key: value for key, value in record.items()
        if str(key) not in _FORMULA_CONTEXT_COLUMNS
    }
    return source_row_fingerprint(source_like)


def _formula_row_current(row) -> bool:
    """Prefer source-content fingerprints; retain timestamp fallback for legacy rows."""
    try:
        payload = json.loads(row["derived_json"])
    except (TypeError, ValueError, json.JSONDecodeError):
        payload = {}
    stored_fingerprint = payload.get(_SOURCE_FINGERPRINT_KEY) if isinstance(payload, dict) else None
    if stored_fingerprint:
        try:
            source_payload = json.loads(row["data_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            return False
        if not isinstance(source_payload, dict):
            return False
        return str(stored_fingerprint) == source_row_fingerprint(source_payload)
    return str(row["source_updated_at"]) == str(row["updated_at"])


def _public_derived_payload(raw: object) -> dict:
    try:
        payload = json.loads(str(raw))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): value for key, value in payload.items() if str(key) != _SOURCE_FINGERPRINT_KEY}


def save_formula_results(
    dataset_id: int,
    mineral_key: str,
    method_id: str,
    method_title: str,
    source_dataframe: pd.DataFrame,
    result_dataframe: pd.DataFrame,
) -> FormulaSaveResult:
    """Persist derived values by immutable analysis_id and stable source chemistry."""
    ensure_formula_storage()
    result_dataframe = _align_result_by_analysis_id(source_dataframe, result_dataframe)
    derived_columns = tuple(
        str(column)
        for column in result_dataframe.columns
        if column not in source_dataframe.columns and not str(column).startswith("_")
    )
    if not derived_columns:
        raise ValueError("Метод не создал новых расчётных колонок")

    analysis_ids = source_dataframe["_analysis_id"].astype(str).tolist()
    now = _utcnow()
    with connect() as con:
        rows = con.execute(
            "SELECT analysis_id, updated_at FROM analysis_rows WHERE dataset_id=?",
            (int(dataset_id),),
        ).fetchall()
        source_versions = {str(row["analysis_id"]): str(row["updated_at"]) for row in rows}
        missing = [analysis_id for analysis_id in analysis_ids if analysis_id not in source_versions]
        if missing:
            raise ValueError("Часть анализов уже отсутствует в базе; обновите страницу и пересчитайте")

        con.execute(
            "DELETE FROM formula_results WHERE dataset_id=? AND method_id=?",
            (int(dataset_id), method_id),
        )
        payload = []
        for row_index, analysis_id in enumerate(analysis_ids):
            derived = {column: result_dataframe.iloc[row_index][column] for column in derived_columns}
            derived[_SOURCE_FINGERPRINT_KEY] = _formula_source_fingerprint(source_dataframe.iloc[row_index].to_dict())
            payload.append((
                int(dataset_id), analysis_id, method_id, source_versions[analysis_id],
                json.dumps(_json_safe_record(derived), ensure_ascii=False), now,
            ))
        con.executemany(
            """
            INSERT INTO formula_results(
                dataset_id, analysis_id, method_id, source_updated_at, derived_json, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            payload,
        )
        con.execute(
            """
            INSERT INTO formula_dataset_state(
                dataset_id, active_method_id, method_title, mineral_key, calculated_at
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(dataset_id) DO UPDATE SET
                active_method_id=excluded.active_method_id,
                method_title=excluded.method_title,
                mineral_key=excluded.mineral_key,
                calculated_at=excluded.calculated_at
            """,
            (int(dataset_id), method_id, method_title, mineral_key, now),
        )
        con.commit()

    return FormulaSaveResult(int(dataset_id), method_id, len(analysis_ids), derived_columns)


def save_point_formula_results(
    dataset_id: int,
    mineral_key: str,
    method_id: str,
    method_title: str,
    source_dataframe: pd.DataFrame,
    result_dataframe: pd.DataFrame,
) -> FormulaSaveResult:
    """Save APFU for a selected mineral subset without changing the dataset default.

    This is used when a point was reclassified after import. It preserves both the
    original chemistry and the earlier calculation, while making the new mineral and
    method the active formula context for exactly those immutable analysis IDs.
    """
    ensure_formula_storage()
    result_dataframe = _align_result_by_analysis_id(source_dataframe, result_dataframe)
    derived_columns = tuple(
        str(column)
        for column in result_dataframe.columns
        if column not in source_dataframe.columns and not str(column).startswith("_")
    )
    if not derived_columns:
        raise ValueError("Метод не создал новых расчётных колонок")
    analysis_ids = source_dataframe["_analysis_id"].astype(str).tolist()
    if not analysis_ids:
        raise ValueError("Нет точек для сохранения")
    marks = ",".join("?" for _ in analysis_ids)
    now = _utcnow()
    with connect() as con:
        rows = con.execute(
            f"SELECT analysis_id, updated_at FROM analysis_rows WHERE dataset_id=? AND analysis_id IN ({marks})",
            [int(dataset_id), *analysis_ids],
        ).fetchall()
        versions = {str(row["analysis_id"]): str(row["updated_at"]) for row in rows}
        missing = [analysis_id for analysis_id in analysis_ids if analysis_id not in versions]
        if missing:
            raise ValueError("Часть анализов уже отсутствует в базе; обновите страницу и пересчитайте")
        payload = []
        states = []
        for row_index, analysis_id in enumerate(analysis_ids):
            derived = {column: result_dataframe.iloc[row_index][column] for column in derived_columns}
            derived[_SOURCE_FINGERPRINT_KEY] = _formula_source_fingerprint(source_dataframe.iloc[row_index].to_dict())
            payload.append((
                int(dataset_id), analysis_id, method_id, versions[analysis_id],
                json.dumps(_json_safe_record(derived), ensure_ascii=False), now,
            ))
            states.append((analysis_id, int(dataset_id), method_id, method_title, mineral_key, now))
        con.executemany(
            """
            INSERT INTO formula_results(
                dataset_id, analysis_id, method_id, source_updated_at, derived_json, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id, method_id) DO UPDATE SET
                dataset_id=excluded.dataset_id,
                source_updated_at=excluded.source_updated_at,
                derived_json=excluded.derived_json,
                calculated_at=excluded.calculated_at
            """,
            payload,
        )
        con.executemany(
            """
            INSERT INTO analysis_formula_state(
                analysis_id, dataset_id, active_method_id, method_title, mineral_key, calculated_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(analysis_id) DO UPDATE SET
                dataset_id=excluded.dataset_id,
                active_method_id=excluded.active_method_id,
                method_title=excluded.method_title,
                mineral_key=excluded.mineral_key,
                calculated_at=excluded.calculated_at
            """,
            states,
        )
        con.commit()
    return FormulaSaveResult(int(dataset_id), method_id, len(analysis_ids), derived_columns)


def _active_state(dataset_id: int) -> dict | None:
    ensure_formula_storage()
    with connect() as con:
        row = con.execute("SELECT * FROM formula_dataset_state WHERE dataset_id=?", (int(dataset_id),)).fetchone()
    return dict(row) if row else None


def formula_status(dataset_id: int) -> FormulaStatus:
    state = _active_state(int(dataset_id))
    with connect() as con:
        total = int(con.execute("SELECT COUNT(*) FROM analysis_rows WHERE dataset_id=?", (int(dataset_id),)).fetchone()[0])
        if not state:
            return FormulaStatus(dataset_id=int(dataset_id), total_rows=total)
        rows = con.execute(
            """
            SELECT fr.source_updated_at, fr.derived_json, a.updated_at, a.data_json
            FROM formula_results fr
            JOIN analysis_rows a ON a.analysis_id=fr.analysis_id
            WHERE fr.dataset_id=? AND fr.method_id=?
            """,
            (int(dataset_id), state["active_method_id"]),
        ).fetchall()

    current = 0
    valid = 0
    invalid = 0
    unknown = 0
    for row in rows:
        if not _formula_row_current(row):
            continue
        current += 1
        payload = _public_derived_payload(row["derived_json"])
        marker = payload.get("formula_valid", None)
        if marker is True:
            valid += 1
        elif marker is False:
            invalid += 1
        else:
            unknown += 1
    return FormulaStatus(
        dataset_id=int(dataset_id),
        method_id=str(state["active_method_id"]),
        method_title=str(state["method_title"]),
        mineral_key=str(state["mineral_key"]),
        total_rows=total,
        current_rows=current,
        stale_rows=max(total - current, 0),
        valid_rows=valid,
        invalid_rows=invalid,
        unknown_validity_rows=unknown,
        calculated_at=str(state["calculated_at"]),
    )


def load_dataset_with_derived(dataset_id: int, include_meta: bool = True) -> pd.DataFrame:
    base = load_dataset_dataframe(int(dataset_id), include_meta=True)
    if base.empty:
        return base if include_meta else base.copy()
    dataset = get_dataset(int(dataset_id))
    default_state = _active_state(int(dataset_id))
    analysis_ids = base["_analysis_id"].astype(str).tolist()
    marks = ",".join("?" for _ in analysis_ids)
    with connect() as con:
        point_rows = con.execute(
            f"SELECT * FROM analysis_formula_state WHERE analysis_id IN ({marks})",
            analysis_ids,
        ).fetchall()
    point_states = {str(row["analysis_id"]): dict(row) for row in point_rows}
    desired_states = {
        analysis_id: point_states.get(analysis_id, default_state)
        for analysis_id in analysis_ids
    }
    method_ids = sorted({
        str(state["active_method_id"])
        for state in desired_states.values() if state and str(state.get("active_method_id") or "")
    })
    current_payloads: dict[str, dict] = {}
    all_columns: set[str] = set()
    if method_ids:
        method_marks = ",".join("?" for _ in method_ids)
        with connect() as con:
            rows = con.execute(
                f"""
                SELECT fr.analysis_id, fr.method_id, fr.source_updated_at, fr.derived_json,
                       a.updated_at, a.data_json
                FROM formula_results fr
                JOIN analysis_rows a ON a.analysis_id=fr.analysis_id
                WHERE fr.dataset_id=? AND fr.method_id IN ({method_marks})
                """,
                [int(dataset_id), *method_ids],
            ).fetchall()
        for row in rows:
            analysis_id = str(row["analysis_id"])
            wanted = desired_states.get(analysis_id)
            if wanted is None or str(row["method_id"]) != str(wanted["active_method_id"]):
                continue
            if not _formula_row_current(row):
                continue
            payload = _public_derived_payload(row["derived_json"])
            current_payloads[analysis_id] = payload
            all_columns.update(str(key) for key in payload)
    if all_columns:
        for column in sorted(all_columns):
            base[column] = [current_payloads.get(analysis_id, {}).get(column) for analysis_id in analysis_ids]

    base = attach_mineral_assignments(base, default_mineral_key=str(dataset["mineral_key"]))
    formula_mineral = {
        analysis_id: str((desired_states.get(analysis_id) or {}).get("mineral_key") or "")
        for analysis_id in analysis_ids
    }
    if all_columns and "Минерал" in base.columns:
        mismatched = base["_analysis_id"].astype(str).map(formula_mineral).fillna("").ne(base["Минерал"].astype(str))
        for column in all_columns:
            base.loc[mismatched, column] = None
    if default_state:
        base.attrs["formula_method_id"] = str(default_state["active_method_id"])
        base.attrs["formula_method_title"] = str(default_state["method_title"])
    if include_meta:
        return base
    return base[[column for column in base.columns if column not in _INTERNAL_META]].copy()


def load_unified_with_derived(project_id: int | None = None, dataset_ids: list[int] | None = None) -> pd.DataFrame:
    if dataset_ids is not None:
        # Plot selections may deliberately include a linked library dataset owned by
        # another project. Resolve only the explicitly selected IDs; do not broaden
        # the scope to every globally stored dataset.
        datasets = [get_dataset(int(dataset_id)) for dataset_id in dict.fromkeys(dataset_ids)]
    else:
        datasets = list_datasets(project_id)
    frames: list[pd.DataFrame] = []
    for dataset in datasets:
        frame = load_dataset_with_derived(int(dataset["id"]), include_meta=True)
        if frame.empty:
            continue
        frame.insert(5 if len(frame.columns) >= 5 else len(frame.columns), "Проект", dataset["project_name"])
        frame.insert(6 if len(frame.columns) >= 6 else len(frame.columns), "Набор", dataset["name"])
        frame.insert(7 if len(frame.columns) >= 7 else len(frame.columns), "Минерал", dataset["mineral_key"])
        frame.insert(8 if len(frame.columns) >= 8 else len(frame.columns), "Источник", dataset["source_filename"])
        frame.insert(9 if len(frame.columns) >= 9 else len(frame.columns), "Лист", dataset["source_sheet"])
        frame.insert(10 if len(frame.columns) >= 10 else len(frame.columns), "Строка Excel", frame["_source_row"])
        frames.append(frame)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True, sort=False)


def active_derived_columns(dataset_ids: Iterable[int]) -> set[str]:
    columns: set[str] = set()
    for dataset_id in {int(value) for value in dataset_ids}:
        state = _active_state(dataset_id)
        if not state:
            continue
        with connect() as con:
            rows = con.execute(
                """
                SELECT fr.derived_json, fr.source_updated_at, a.updated_at, a.data_json
                FROM formula_results fr
                JOIN analysis_rows a ON a.analysis_id=fr.analysis_id
                WHERE fr.dataset_id=? AND fr.method_id=?
                """,
                (dataset_id, state["active_method_id"]),
            ).fetchall()
        for row in rows:
            if _formula_row_current(row):
                columns.update(_public_derived_payload(row["derived_json"]).keys())
    return columns


def formula_provenance_rows(dataset_ids: Iterable[int] | None = None) -> list[dict]:
    wanted = None if dataset_ids is None else {int(value) for value in dataset_ids}
    rows = []
    for dataset in list_datasets():
        dataset_id = int(dataset["id"])
        if wanted is not None and dataset_id not in wanted:
            continue
        status = formula_status(dataset_id)
        if not status.has_active_formula:
            continue
        rows.append({
            "dataset_id": dataset_id,
            "Набор": dataset["name"],
            "Минерал": dataset["mineral_key"],
            "Метод": status.method_title or status.method_id,
            "method_id": status.method_id,
            "Fresh rows": status.current_rows,
            "Valid formula rows": status.valid_rows,
            "Invalid formula rows": status.invalid_rows,
            "Unknown validity (legacy)": status.unknown_validity_rows,
            "Устаревших строк": status.stale_rows,
            "Рассчитано": status.calculated_at,
        })
    return rows

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Iterable

import pandas as pd

from petrolab.db import (
    _json_safe_record,
    _utcnow,
    connect,
    list_datasets,
    load_dataset_dataframe,
)


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
    calculated_at: str = ""

    @property
    def has_active_formula(self) -> bool:
        return bool(self.method_id)


_INTERNAL_META = {
    "_analysis_id",
    "_dataset_id",
    "_project_id",
    "_row_index",
    "_source_row",
}


def ensure_formula_storage() -> None:
    """Create formula-result tables without mixing derived values into source data_json."""
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
            "CREATE INDEX IF NOT EXISTS idx_formula_results_dataset_method "
            "ON formula_results(dataset_id, method_id)"
        )
        con.commit()


def save_formula_results(
    dataset_id: int,
    mineral_key: str,
    method_id: str,
    method_title: str,
    source_dataframe: pd.DataFrame,
    result_dataframe: pd.DataFrame,
) -> FormulaSaveResult:
    """Persist only columns produced by the selected formula method.

    Results are keyed by immutable analysis_id and remember the exact source-row update
    timestamp. A later edit/refresh therefore makes only the affected result stale instead
    of silently presenting an old formula as current.
    """
    ensure_formula_storage()
    if "_analysis_id" not in source_dataframe.columns:
        raise ValueError("Для сохранения пересчёта требуется _analysis_id")
    if len(source_dataframe) != len(result_dataframe):
        raise ValueError("Число исходных и рассчитанных строк не совпадает")

    derived_columns = tuple(
        str(column)
        for column in result_dataframe.columns
        if column not in source_dataframe.columns and not str(column).startswith("_")
    )
    if not derived_columns:
        raise ValueError("Метод не создал новых расчётных колонок")

    analysis_ids = source_dataframe["_analysis_id"].astype(str).tolist()
    if len(set(analysis_ids)) != len(analysis_ids):
        raise ValueError("В наборе обнаружены повторяющиеся _analysis_id")

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
            derived = {
                column: result_dataframe.iloc[row_index][column]
                for column in derived_columns
            }
            payload.append(
                (
                    int(dataset_id),
                    analysis_id,
                    method_id,
                    source_versions[analysis_id],
                    json.dumps(_json_safe_record(derived), ensure_ascii=False),
                    now,
                )
            )
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

    return FormulaSaveResult(
        dataset_id=int(dataset_id),
        method_id=method_id,
        row_count=len(analysis_ids),
        derived_columns=derived_columns,
    )


def _active_state(dataset_id: int) -> dict | None:
    ensure_formula_storage()
    with connect() as con:
        row = con.execute(
            "SELECT * FROM formula_dataset_state WHERE dataset_id=?",
            (int(dataset_id),),
        ).fetchone()
    return dict(row) if row else None


def formula_status(dataset_id: int) -> FormulaStatus:
    state = _active_state(int(dataset_id))
    with connect() as con:
        total = int(
            con.execute(
                "SELECT COUNT(*) FROM analysis_rows WHERE dataset_id=?",
                (int(dataset_id),),
            ).fetchone()[0]
        )
        if not state:
            return FormulaStatus(dataset_id=int(dataset_id), total_rows=total)
        rows = con.execute(
            """
            SELECT fr.source_updated_at, a.updated_at
            FROM formula_results fr
            JOIN analysis_rows a ON a.analysis_id=fr.analysis_id
            WHERE fr.dataset_id=? AND fr.method_id=?
            """,
            (int(dataset_id), state["active_method_id"]),
        ).fetchall()
    current = sum(1 for row in rows if str(row["source_updated_at"]) == str(row["updated_at"]))
    return FormulaStatus(
        dataset_id=int(dataset_id),
        method_id=str(state["active_method_id"]),
        method_title=str(state["method_title"]),
        mineral_key=str(state["mineral_key"]),
        total_rows=total,
        current_rows=current,
        stale_rows=max(total - current, 0),
        calculated_at=str(state["calculated_at"]),
    )


def load_dataset_with_derived(dataset_id: int, include_meta: bool = True) -> pd.DataFrame:
    """Load source values plus current derived columns from the active formula method."""
    base = load_dataset_dataframe(int(dataset_id), include_meta=True)
    if base.empty:
        return base if include_meta else base.copy()

    state = _active_state(int(dataset_id))
    if state:
        with connect() as con:
            rows = con.execute(
                """
                SELECT fr.analysis_id, fr.source_updated_at, fr.derived_json, a.updated_at
                FROM formula_results fr
                JOIN analysis_rows a ON a.analysis_id=fr.analysis_id
                WHERE fr.dataset_id=? AND fr.method_id=?
                """,
                (int(dataset_id), state["active_method_id"]),
            ).fetchall()
        current_payloads: dict[str, dict] = {}
        all_columns: set[str] = set()
        for row in rows:
            if str(row["source_updated_at"]) != str(row["updated_at"]):
                continue
            payload = json.loads(row["derived_json"])
            current_payloads[str(row["analysis_id"])] = payload
            all_columns.update(str(key) for key in payload)
        if all_columns:
            id_series = base["_analysis_id"].astype(str)
            for column in sorted(all_columns):
                base[column] = [
                    current_payloads.get(analysis_id, {}).get(column)
                    for analysis_id in id_series
                ]
        base.attrs["formula_method_id"] = str(state["active_method_id"])
        base.attrs["formula_method_title"] = str(state["method_title"])

    if include_meta:
        return base
    return base[[column for column in base.columns if column not in _INTERNAL_META]].copy()


def load_unified_with_derived(
    project_id: int | None = None,
    dataset_ids: list[int] | None = None,
) -> pd.DataFrame:
    datasets = list_datasets(project_id)
    if dataset_ids is not None:
        wanted = {int(value) for value in dataset_ids}
        datasets = [dataset for dataset in datasets if int(dataset["id"]) in wanted]

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
                SELECT fr.derived_json, fr.source_updated_at, a.updated_at
                FROM formula_results fr
                JOIN analysis_rows a ON a.analysis_id=fr.analysis_id
                WHERE fr.dataset_id=? AND fr.method_id=?
                """,
                (dataset_id, state["active_method_id"]),
            ).fetchall()
        for row in rows:
            if str(row["source_updated_at"]) == str(row["updated_at"]):
                columns.update(json.loads(row["derived_json"]).keys())
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
        rows.append(
            {
                "dataset_id": dataset_id,
                "Набор": dataset["name"],
                "Минерал": dataset["mineral_key"],
                "Метод": status.method_title or status.method_id,
                "method_id": status.method_id,
                "Актуальных строк": status.current_rows,
                "Устаревших строк": status.stale_rows,
                "Рассчитано": status.calculated_at,
            }
        )
    return rows

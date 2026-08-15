"""Safe automatic post-import processing for probe/EDS chemistry.

The pipeline only acts on chemically high-confidence rows.  Ambiguous points,
trace-only datasets and robust-screening outliers stay unresolved for manual
review.  Formula/APFU results are persisted as derived data and never replace
source chemistry.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from petrolab.db import connect, get_dataset, load_dataset_dataframe
from petrolab.derived import save_formula_results
from petrolab.formula_workflow import recommended_method
from petrolab.phase_suggestions import (
    PHASE_SUGGESTION_RULESET_VERSION,
    SUGGESTED_MINERAL_COLUMN,
    SUGGESTION_CONFIDENCE_COLUMN,
    attach_phase_suggestions,
    materialize_confirmed_phases,
)
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.workflow_screening import OUTLIER_COLUMN, attach_chemical_outlier_screen


_MAJOR_PHASE_COLUMNS = {
    "SiO2", "TiO2", "Al2O3", "Cr2O3", "FeO", "FeOt", "Fe2O3", "MgO",
    "CaO", "Na2O", "K2O", "P2O5",
}


@dataclass(frozen=True)
class AutoDatasetReport:
    source_dataset_id: int
    working_dataset_ids: tuple[int, ...]
    phase_dataset_ids: tuple[int, ...]
    auto_assigned_rows: int
    unresolved_rows: int
    formula_datasets: tuple[int, ...]
    formula_invalid_rows: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class AutoImportReport:
    datasets: tuple[AutoDatasetReport, ...]

    @property
    def working_dataset_ids(self) -> tuple[int, ...]:
        values: list[int] = []
        for report in self.datasets:
            values.extend(report.working_dataset_ids)
        return tuple(dict.fromkeys(values))

    @property
    def auto_assigned_rows(self) -> int:
        return sum(item.auto_assigned_rows for item in self.datasets)

    @property
    def unresolved_rows(self) -> int:
        return sum(item.unresolved_rows for item in self.datasets)

    @property
    def formula_datasets(self) -> int:
        return sum(len(item.formula_datasets) for item in self.datasets)


def _row_count(dataset_id: int) -> int:
    dataset = get_dataset(int(dataset_id))
    return int(dataset.get("row_count") or 0) if dataset else 0


def _mark_auto_annotations(analysis_ids: list[str]) -> None:
    if not analysis_ids:
        return
    marks = ",".join("?" for _ in analysis_ids)
    source = f"auto_high_confidence:{PHASE_SUGGESTION_RULESET_VERSION}"
    with connect() as con:
        # materialize_confirmed_phases records exact labels in the generic annotation
        # table.  Preserve those labels but make the provenance explicit: this was an
        # automatic high-confidence assignment, not a human confirmation.
        con.execute(
            f"""UPDATE analysis_annotations SET source=?, updated_at=CURRENT_TIMESTAMP
                WHERE namespace='phase' AND key='confirmed_phase'
                  AND analysis_id IN ({marks})""",
            [source, *analysis_ids],
        )
        con.commit()


def _calculate_default_formula(dataset_id: int) -> tuple[bool, int, str]:
    dataset = get_dataset(int(dataset_id))
    if not dataset:
        return False, 0, "dataset disappeared before formula calculation"
    mineral_key = str(dataset.get("mineral_key") or "generic")
    method = recommended_method(mineral_key)
    if method is None:
        return False, 0, ""
    source = load_dataset_dataframe(int(dataset_id), include_meta=True)
    if source.empty:
        return False, 0, ""
    try:
        result = calculate_formula_safe(source, mineral_key, method.id)
        save_formula_results(
            dataset_id=int(dataset_id),
            mineral_key=mineral_key,
            method_id=method.id,
            method_title=method.title_ru,
            source_dataframe=source,
            result_dataframe=result.data,
        )
    except Exception as exc:
        return False, 0, str(exc)
    invalid = 0
    if "formula_valid" in result.data.columns:
        invalid = int((~result.data["formula_valid"].fillna(False).astype(bool)).sum())
    return True, invalid, ""


def auto_process_dataset(project_id: int, dataset_id: int) -> AutoDatasetReport:
    dataset = get_dataset(int(dataset_id))
    if not dataset:
        raise ValueError("Импортированный dataset не найден")
    warnings: list[str] = []
    phase_dataset_ids: list[int] = []
    formula_dataset_ids: list[int] = []
    formula_invalid_rows = 0
    auto_assigned = 0

    mineral_key = str(dataset.get("mineral_key") or "generic")
    if mineral_key != "generic":
        phase_dataset_ids = [int(dataset_id)]
    else:
        frame = load_dataset_dataframe(int(dataset_id), include_meta=True)
        major_count = len(_MAJOR_PHASE_COLUMNS.intersection(frame.columns))
        if frame.empty:
            return AutoDatasetReport(
                int(dataset_id), (int(dataset_id),), (), 0, 0, (), 0, (),
            )
        if major_count < 3:
            warnings.append(
                "Trace-only/LA набор не разбирался по фазам автоматически: минерал нужно получить из физической связи или назначить вручную."
            )
        else:
            suggested = attach_phase_suggestions(frame)
            screened = attach_chemical_outlier_screen(
                suggested, group_column=SUGGESTED_MINERAL_COLUMN
            )
            phase = screened[SUGGESTED_MINERAL_COLUMN].fillna("").astype(str).str.strip()
            confidence = screened[SUGGESTION_CONFIDENCE_COLUMN].fillna("").astype(str)
            outlier = screened.get(
                OUTLIER_COLUMN, pd.Series(False, index=screened.index)
            ).fillna(False).astype(bool)
            safe = confidence.eq("high") & phase.ne("") & ~outlier
            assignments = {
                str(row["_analysis_id"]): str(row[SUGGESTED_MINERAL_COLUMN]).strip()
                for _, row in screened.loc[safe].iterrows()
                if str(row.get("_analysis_id") or "").strip()
            }
            if assignments:
                created = materialize_confirmed_phases(int(dataset_id), assignments)
                phase_dataset_ids = list(dict.fromkeys(int(value) for value in created.values()))
                auto_assigned = len(assignments)
                _mark_auto_annotations(list(assignments))

    for child_id in phase_dataset_ids:
        ok, invalid, warning = _calculate_default_formula(int(child_id))
        if ok:
            formula_dataset_ids.append(int(child_id))
            formula_invalid_rows += int(invalid)
        elif warning:
            warnings.append(f"Набор {child_id}: APFU не сохранён автоматически — {warning}")

    unresolved = _row_count(int(dataset_id)) if mineral_key == "generic" else 0
    working: list[int] = list(phase_dataset_ids)
    if unresolved or not working:
        working.append(int(dataset_id))
    return AutoDatasetReport(
        source_dataset_id=int(dataset_id),
        working_dataset_ids=tuple(dict.fromkeys(working)),
        phase_dataset_ids=tuple(phase_dataset_ids),
        auto_assigned_rows=int(auto_assigned),
        unresolved_rows=int(unresolved),
        formula_datasets=tuple(formula_dataset_ids),
        formula_invalid_rows=int(formula_invalid_rows),
        warnings=tuple(warnings),
    )


def auto_process_imported_datasets(project_id: int, dataset_ids: list[int] | tuple[int, ...]) -> AutoImportReport:
    reports = tuple(auto_process_dataset(int(project_id), int(dataset_id)) for dataset_id in dataset_ids)
    return AutoImportReport(reports)

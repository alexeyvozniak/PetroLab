from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd

from petrolab.ui.table_view_state import TableViewState


@dataclass(frozen=True, slots=True)
class TableViewPreset:
    name: str
    description: str
    state: TableViewState


_METHOD_COLUMNS = ("Method", "Метод", "Analytical method", "Метод анализа")
_QC_COLUMNS = ("QC решение", "QC уровень", "QC", "Quality", "Quality status", "Status", "Статус")
_MINERAL_COLUMNS = ("Минерал", "Mineral")
_LA_PATTERN = re.compile(r"(?:\bla\s*[-–— ]?\s*icp\s*[-–— ]?\s*ms\b|laser\s+ablation|лазер)", re.IGNORECASE)
_POOR_QC_PATTERN = re.compile(r"(?:poor|bad|fail|failed|reject|rejected|warn|warning|низк|плох|неуд|отклон|брак)", re.IGNORECASE)
_MICA_PATTERN = re.compile(r"(?:mica|слюд|phlogopite|biotite|muscovite|annite|lepidolite|zinnwaldite)", re.IGNORECASE)


def _first_present(dataframe: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    return next((column for column in candidates if column in dataframe.columns), None)


def _matching_values(series: pd.Series, pattern: re.Pattern[str]) -> list[str]:
    values = sorted({str(value).strip() for value in series.dropna().tolist() if str(value).strip()}, key=str.casefold)
    return [value for value in values if pattern.search(value)]


def builtin_table_view_presets(dataframe: pd.DataFrame) -> list[TableViewPreset]:
    """Return only presets that make semantic sense for the current data universe.

    Presets are presentation state only. They never contain analysis IDs and do
    not represent Selection, Hide, Exclude, Work Group or Generation.
    """
    presets = [
        TableViewPreset(
            "Все анализы",
            "Сбросить поиск/фильтр/группировку и вернуться к компактному основному виду.",
            TableViewState(column_mode="Основное"),
        )
    ]
    if dataframe.empty:
        return presets

    method_col = _first_present(dataframe, _METHOD_COLUMNS)
    if method_col:
        values = _matching_values(dataframe[method_col], _LA_PATTERN)
        if values:
            presets.append(
                TableViewPreset(
                    "LA-ICP-MS",
                    f"Только строки метода {', '.join(values[:3])}; trace-поля впереди.",
                    TableViewState(
                        column_mode="Trace",
                        filter_column=method_col,
                        filter_values=values,
                    ),
                )
            )

    qc_col = _first_present(dataframe, _QC_COLUMNS)
    if qc_col:
        values = _matching_values(dataframe[qc_col], _POOR_QC_PATTERN)
        if values:
            presets.append(
                TableViewPreset(
                    "Poor QC",
                    f"Строки с проблемным QC по полю «{qc_col}».",
                    TableViewState(
                        column_mode="QC",
                        filter_column=qc_col,
                        filter_values=values,
                    ),
                )
            )

    mineral_col = _first_present(dataframe, _MINERAL_COLUMNS)
    if mineral_col:
        values = _matching_values(dataframe[mineral_col], _MICA_PATTERN)
        if values:
            presets.append(
                TableViewPreset(
                    "Слюды",
                    "Слюды текущего рабочего контекста; микрозондовые поля впереди.",
                    TableViewState(
                        column_mode="Микрозонд",
                        filter_column=mineral_col,
                        filter_values=values,
                    ),
                )
            )
    return presets

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import display_value, human_point_label
from petrolab.db import get_dataset
from petrolab.generations import PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN
from petrolab.source_registry import SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN
from petrolab.ui.components import collect_related_images, render_asset_gallery
from petrolab.ui.field_presets import apfu_columns, microprobe_columns, qc_columns, trace_columns


_IDENTITY_FIELDS = (
    "Sample", "Grain", "Point", "Минерал", "Mineral",
    PETROLAB_GENERATION_COLUMN, SOURCE_GENERATION_COLUMN, "Generation",
    WORK_GROUP_COLUMN, "Textural zone",
)
_METHOD_FIELDS = ("Method", "Метод", "Analytical method", "Метод анализа")


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    try:
        if pd.isna(value):
            return False
    except (TypeError, ValueError):
        pass
    return bool(str(value).strip())


def _unique_columns(*groups: list[str] | tuple[str, ...]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for column in group:
            if column not in result:
                result.append(column)
    return result


def record_identity(row: pd.Series) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for column in _IDENTITY_FIELDS:
        if column in row.index and _nonempty(row.get(column)):
            result.append((str(column), display_value(row.get(column))))
    return result


def record_measurement_columns(dataframe: pd.DataFrame) -> dict[str, list[str]]:
    microprobe = microprobe_columns(dataframe)
    trace = trace_columns(dataframe)
    apfu = apfu_columns(dataframe)
    qc = qc_columns(dataframe)
    used = set(microprobe) | set(trace) | set(apfu) | set(qc)
    return {
        "Микрозонд": microprobe,
        "Trace": [column for column in trace if column not in set(microprobe)],
        "APFU": [column for column in apfu if column not in set(microprobe) | set(trace)],
        "QC": [column for column in qc if column not in set(microprobe) | set(trace) | set(apfu)],
        "Прочее": [
            str(column) for column in dataframe.columns
            if not str(column).startswith("_")
            and str(column) not in used
            and str(column) not in _IDENTITY_FIELDS
            and str(column) not in _METHOD_FIELDS
            and str(column) not in {SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, "Набор", "Источник"}
        ],
    }


def record_provenance(row: pd.Series) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    dataset_id = row.get("_dataset_id")
    dataset = None
    if _nonempty(dataset_id):
        try:
            dataset = get_dataset(int(dataset_id))
        except (TypeError, ValueError):
            dataset = None

    if dataset:
        for label, key in (
            ("Массив", "name"),
            ("Файл", "source_filename"),
            ("Лист", "source_sheet"),
            ("Тип источника", "source_kind"),
        ):
            value = dataset.get(key)
            if _nonempty(value):
                result.append((label, display_value(value)))

    source_row = row.get("_source_row")
    if _nonempty(source_row):
        result.append(("Строка источника", display_value(source_row)))
    for column in _METHOD_FIELDS:
        if column in row.index and _nonempty(row.get(column)):
            result.append(("Метод", display_value(row.get(column))))
            break
    if SOURCE_LABEL_COLUMN in row.index and _nonempty(row.get(SOURCE_LABEL_COLUMN)):
        result.append(("Источник / статья", display_value(row.get(SOURCE_LABEL_COLUMN))))
    if SOURCE_TABLE_COLUMN in row.index and _nonempty(row.get(SOURCE_TABLE_COLUMN)):
        result.append(("Таблица источника", display_value(row.get(SOURCE_TABLE_COLUMN))))
    return result


def _value_frame(row: pd.Series, columns: list[str]) -> pd.DataFrame:
    present = [column for column in columns if column in row.index and _nonempty(row.get(column))]
    return pd.DataFrame(
        {
            "Параметр": present,
            "Значение": [display_value(row.get(column)) for column in present],
        }
    )


def _pairs_frame(pairs: list[tuple[str, str]]) -> pd.DataFrame:
    return pd.DataFrame(pairs, columns=["Поле", "Значение"])


def render_record_detail(
    row: pd.Series,
    dataframe: pd.DataFrame,
    *,
    project_id: int | None,
) -> None:
    """Render one scientific record without exposing internal database keys."""
    label = human_point_label(row)
    identity = record_identity(row)
    if identity:
        compact = " · ".join(value for _, value in identity[:6])
        st.caption(compact)

    sections = record_measurement_columns(dataframe)
    chemistry_columns = _unique_columns(sections["Микрозонд"], sections["Trace"])
    calculation_columns = _unique_columns(sections["APFU"], sections["QC"])
    chemistry = _value_frame(row, chemistry_columns)
    calculations = _value_frame(row, calculation_columns)
    provenance = _pairs_frame(record_provenance(row))

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.markdown("**Химия**")
        if chemistry.empty:
            st.caption("Химические значения для этой точки не найдены.")
        else:
            st.dataframe(chemistry, width="stretch", hide_index=True, height=min(420, 36 * (len(chemistry) + 1)))

        if not calculations.empty:
            st.markdown("**APFU / QC**")
            st.dataframe(calculations, width="stretch", hide_index=True, height=min(320, 36 * (len(calculations) + 1)))

    with right:
        st.markdown("**Источник и provenance**")
        if provenance.empty:
            st.caption("Дополнительные сведения об источнике не зарегистрированы.")
        else:
            st.dataframe(provenance, width="stretch", hide_index=True, height=min(300, 36 * (len(provenance) + 1)))

        assets = collect_related_images(row, project_id=project_id)
        st.markdown(f"**Изображения · {len(assets)}**")
        if assets:
            render_asset_gallery(assets, max_items=8, width="stretch")
        else:
            st.caption("К этой точке пока не привязаны изображения.")

    # Keep the label available to accessibility tools even when the compact
    # identity caption had to omit some fields.
    st.caption(f"Точка: {label}")

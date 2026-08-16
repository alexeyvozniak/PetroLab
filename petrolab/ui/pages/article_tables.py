from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.article_tables import article_table_xlsx_bytes, format_dataframe_for_article
from petrolab.analysis_groups import attach_work_groups
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.publication_manifest import append_manifest_to_xlsx, build_selection_manifest, manifest_json_bytes
from petrolab.repositories.rock_repository import composition_wide
from petrolab.settings_service import load_settings
from petrolab.source_registry import (
    SOURCE_CITATION_COLUMN,
    SOURCE_DOI_COLUMN,
    SOURCE_LABEL_COLUMN,
    SOURCE_TABLE_COLUMN,
    attach_study_metadata,
)
from petrolab.ui.components import render_project_selector
from petrolab.ui.data_scope import render_analysis_scope
from petrolab.ui.exact_route import persist_exact_route, render_exact_route_banner
from petrolab.visualization_presets import TABLE_PRESETS

_EXACT_A = "_article_table_exact_analysis_ids"
_EXACT_D = "_article_table_exact_dataset_ids"
_EXACT_C = "_article_table_exact_context"


def _column_selector(dataframe: pd.DataFrame, key: str) -> list[str]:
    meta = [
        column for column in [
            "Project", "Проект", "Rock", "Sample", "Grain", "Point", "Generation",
            "Набор", "Минерал", SOURCE_LABEL_COLUMN, SOURCE_CITATION_COLUMN,
            SOURCE_DOI_COLUMN, SOURCE_TABLE_COLUMN, "Massif", "Lithology", "Age_Ma",
        ]
        if column in dataframe.columns
    ]
    chemistry = [column for column in dataframe.columns if not str(column).startswith("_") and column not in meta]
    ordered = meta + chemistry
    defaults = ordered[: min(24, len(ordered))]
    return st.multiselect("Колонки таблицы", ordered, default=defaults, key=key)


def _render_table(
    dataframe: pd.DataFrame,
    key_prefix: str,
    default_title: str,
    *,
    manifest: dict | None = None,
) -> None:
    if dataframe.empty:
        st.info("Нет данных для таблицы.")
        return
    columns = _column_selector(dataframe, f"{key_prefix}_columns")
    if not columns:
        return
    settings = load_settings()
    preset_names = list(TABLE_PRESETS)
    preferred = str(settings.get("default_table_preset", "Lithos"))
    c1, c2 = st.columns(2)
    preset = c1.selectbox(
        "Журнальный preset",
        preset_names,
        index=preset_names.index(preferred) if preferred in preset_names else 0,
        key=f"{key_prefix}_preset",
    )
    title = c2.text_input("Название таблицы", value=default_title, key=f"{key_prefix}_title")
    note = st.text_area("Примечание под таблицей", key=f"{key_prefix}_note", height=80)
    formatted = format_dataframe_for_article(dataframe, preset_name=preset, columns=columns)
    st.dataframe(formatted, width="stretch", height=520, hide_index=True)
    st.caption(TABLE_PRESETS[preset].note or "Preset задаёт шрифт, округление и ориентацию страницы; содержимое колонок остаётся под вашим контролем.")
    data = article_table_xlsx_bytes(formatted, preset_name=preset, title=title, note=note)
    if manifest is not None:
        data = append_manifest_to_xlsx(manifest=manifest, workbook_bytes=data)
    st.download_button(
        "Скачать оформленный XLSX" + (" + manifest" if manifest is not None else ""),
        data,
        file_name=f"{key_prefix}_{preset.replace(' ', '_')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"{key_prefix}_download",
    )
    if manifest is not None:
        st.download_button(
            "JSON manifest",
            manifest_json_bytes(manifest),
            file_name=f"{key_prefix}_manifest.json",
            mime="application/json",
            key=f"{key_prefix}_manifest_download",
        )


def render_article_tables_page() -> None:
    st.title("Таблицы для статьи")
    st.write(
        "Конструктор публикационных таблиц с одинаковой логикой для минералов и валовых составов. "
        "Preset отвечает за оформление, а выбор строк и колонок остаётся полностью ручным."
    )
    exact_ids, _, _ = persist_exact_route(
        st.session_state,
        incoming_analysis_key="workflow_table_analysis_ids",
        incoming_dataset_key="workflow_table_dataset_ids",
        incoming_context_key="workflow_table_context",
        persistent_analysis_key=_EXACT_A,
        persistent_dataset_key=_EXACT_D,
        persistent_context_key=_EXACT_C,
    )
    render_exact_route_banner(
        count=len(exact_ids),
        label="Вернуться к обычному конструктору таблицы",
        reset_key="article_table_reset_exact",
        persistent_keys=(_EXACT_A, _EXACT_D, _EXACT_C),
        incoming_keys=("workflow_table_analysis_ids", "workflow_table_dataset_ids", "workflow_table_context"),
    )

    selected_analysis_ids = {
        str(value) for value in st.session_state.pop("workflow_table_analysis_ids", [])
    }
    selected_dataset_ids = [
        int(value) for value in st.session_state.pop("workflow_table_dataset_ids", [])
    ]
    selected_context = st.session_state.pop("workflow_table_context", {})
    if selected_analysis_ids and selected_dataset_ids:
        dataframe = attach_study_metadata(
            attach_generations(
                attach_work_groups(load_unified_with_derived(None, selected_dataset_ids))
            )
        )
        dataframe = dataframe[dataframe["_analysis_id"].astype(str).isin(selected_analysis_ids)].copy()
        st.success(
            f"Таблица использует тот же сохранённый отбор: {len(dataframe)} точек."
        )
        if selected_context:
            st.caption("Фильтры исходного отбора сохранены в контексте перехода; здесь можно менять только представление таблицы.")
        manifest = build_selection_manifest(
            kind="supplementary_table",
            dataframe=dataframe,
            dataset_ids=selected_dataset_ids,
            filters={"database_selection": selected_context},
        )
        _render_table(
            dataframe,
            "selection_table",
            "Supplementary mineral compositions",
            manifest=manifest,
        )
        return

    mode = st.segmented_control(
        "Данные",
        ["Минеральные анализы", "Валовые составы пород"],
        default="Минеральные анализы",
        key="article_table_mode",
    )
    if mode == "Минеральные анализы":
        scope = render_analysis_scope("article_table")
        if scope is None:
            return
        _render_table(scope.dataframe, "mineral_table", "Mineral compositions")
    else:
        project = render_project_selector("article_table_rocks_project")
        if project is None:
            return
        dataframe = composition_wide(int(project["id"]))
        _render_table(dataframe, "rock_table", "Whole-rock compositions")

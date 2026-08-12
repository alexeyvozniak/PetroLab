from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import (
    apply_quick_filter,
    compute_changes,
    dataset_label,
    display_value,
    row_identity,
)
from petrolab.db import META_COLUMNS, list_datasets, list_projects
from petrolab.derived import active_derived_columns, load_unified_with_derived
from petrolab.services.analysis_service import save_changes_and_sync, save_changes_to_database
from petrolab.ui.components import (
    collect_related_images,
    render_asset_gallery,
    render_project_selector,
)


PROTECTED_ANALYSIS_COLUMNS = META_COLUMNS | {"Σ оксидов", "QC суммы"}


def _render_point_card(dataframe: pd.DataFrame, project_id: int | None) -> None:
    if dataframe.empty:
        return

    point_map = {
        (
            f"{row_identity(row)} · {row.get('Источник', '')} · "
            f"строка {row.get('_source_row', '—')} · {str(row['_analysis_id'])[:8]}"
        ): str(row["_analysis_id"])
        for _, row in dataframe.head(3000).iterrows()
    }
    selected_label = st.selectbox("Точка", list(point_map), key="db_point_card")
    analysis_id = point_map[selected_label]
    selected_row = dataframe[dataframe["_analysis_id"].astype(str) == analysis_id].iloc[0]

    visible_columns = [column for column in dataframe.columns if not str(column).startswith("_")]
    properties = pd.DataFrame(
        {
            "Параметр": visible_columns,
            "Значение": [display_value(selected_row.get(column)) for column in visible_columns],
        }
    )
    st.dataframe(properties, width="stretch", hide_index=True, height=360)
    render_asset_gallery(collect_related_images(selected_row, project_id=project_id))


def render_analyses_page() -> None:
    """Render source and current derived values in one user-facing analysis table."""
    st.title("Единая база анализов")

    if not list_projects():
        st.info("Сначала создайте проект и импортируйте данные.")
        st.stop()

    scope = st.radio("Область", ["Один проект", "Все проекты"], horizontal=True)
    project_id: int | None = None
    if scope == "Один проект":
        project = render_project_selector("db_project")
        if project is None:
            st.stop()
        project_id = int(project["id"])

    datasets = list_datasets(project_id)
    if not datasets:
        st.info("В выбранной области нет данных.")
        st.stop()

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    selected_labels = st.multiselect("Наборы данных", list(labels), default=list(labels))
    selected_ids = [labels[label] for label in selected_labels]
    if not selected_ids:
        st.stop()

    dataframe = load_unified_with_derived(project_id, selected_ids)
    if dataframe.empty:
        st.info("В выбранных наборах нет аналитических строк.")
        st.stop()

    derived_columns = active_derived_columns(selected_ids)
    if derived_columns:
        st.caption(
            "Расчётные поля уже включены в таблицу. Они защищены от ручного редактирования и "
            "никогда не записываются обратно в исходный Excel; обновить их можно через «Расчёты и формулы»."
        )

    query = st.text_input("Поиск по всей выбранной базе", key="db_search")
    shown = apply_quick_filter(dataframe, query).copy()

    protected_columns = PROTECTED_ANALYSIS_COLUMNS | set(derived_columns)
    disabled_columns = [
        column
        for column in shown.columns
        if column in protected_columns or str(column).startswith("_")
    ]
    edited = st.data_editor(
        shown,
        width="stretch",
        hide_index=True,
        height=650,
        disabled=disabled_columns,
        num_rows="fixed",
        key="unified_editor",
    )
    changes = compute_changes(
        shown,
        edited,
        protected_columns=protected_columns,
    )

    if changes:
        st.caption(f"Несохранённых изменений: {len(changes)}")

    save_db_col, sync_col = st.columns(2)
    if save_db_col.button(
        "Сохранить изменения в базе",
        type="primary",
        disabled=not changes,
        width="stretch",
    ):
        result = save_changes_to_database(changes)
        if result.ok:
            st.success(f"Сохранено изменений: {result.saved_changes}.")
            st.rerun()
        for error in result.errors:
            st.error(error)

    if sync_col.button(
        "Сохранить в базе и записать в Excel",
        disabled=not changes,
        width="stretch",
    ):
        result = save_changes_and_sync(changes)
        if result.ok:
            st.success(
                f"Сохранено изменений: {result.saved_changes}; "
                f"обновлено Excel-файлов: {result.synced_files}."
            )
            st.rerun()
        for error in result.errors:
            st.error(error)

    with st.expander("Карточка точки и связанные изображения"):
        _render_point_card(shown, project_id)

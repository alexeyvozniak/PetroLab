from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import display_value, row_identity
from petrolab.db import META_COLUMNS
from petrolab.mineral_assignments import assign_mineral, assignment_history
from petrolab.minerals.registry import MINERALS
from petrolab.ui.components import collect_related_images, render_asset_gallery


PROTECTED_ANALYSIS_COLUMNS = META_COLUMNS | {
    "Σ оксидов",
    "QC суммы",
    "QC химии",
    "QC железа",
    WORK_GROUP_COLUMN,
}


def render_point_card(dataframe: pd.DataFrame, project_id: int | None) -> None:
    if dataframe.empty:
        return

    point_map = {
        (
            f"{row_identity(row)} · {row.get('Источник', '')} · "
            f"строка {row.get('_source_row', '—')} · {str(row['_analysis_id'])[:8]}"
        ): str(row["_analysis_id"])
        for _, row in dataframe.head(3000).iterrows()
    }
    if not point_map:
        return
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

    with st.expander("Проверить минерал / исправить отнесение", expanded=False):
        dataset_mineral = str(selected_row.get("Минерал исходного набора") or selected_row.get("Минерал") or "")
        effective_mineral = str(selected_row.get("Минерал") or dataset_mineral)
        options = ["__dataset__"] + list(MINERALS)
        selected_key = st.selectbox(
            "Минерал для этой точки",
            options,
            index=options.index(effective_mineral) if effective_mineral in options else 0,
            format_func=lambda value: (
                "Вернуть минерал набора · " + dataset_mineral
                if value == "__dataset__"
                else MINERALS[value].name_ru
            ),
            key=f"point_mineral_{analysis_id}",
            help="Это не меняет исходный Excel и не удаляет анализ. Меняется только интерпретация точки с историей правок.",
        )
        reason = st.text_input(
            "Почему изменено · необязательно",
            value=str(selected_row.get("Комментарий переотнесения") or ""),
            placeholder="например, выброс на графике; проверено по BSE",
            key=f"point_mineral_reason_{analysis_id}",
        )
        target = None if selected_key == "__dataset__" else selected_key
        if st.button("Сохранить отнесение", key=f"save_point_mineral_{analysis_id}", width="stretch"):
            try:
                change = assign_mineral(analysis_id, target, reason=reason)
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                if change.changed:
                    st.success(
                        "Отнесение сохранено. Прежняя химия и исходный минерал набора сохранены; "
                        "APFU для несовпадающего минерала будет показан пустым до нового пересчёта."
                    )
                    st.rerun()
                else:
                    st.caption("Изменений нет.")
        history = assignment_history(analysis_id)
        if history:
            st.caption("История интерпретации точки")
            st.dataframe(
                pd.DataFrame(history).rename(columns={
                    "previous_mineral_key": "Было",
                    "mineral_key": "Стало",
                    "reason": "Комментарий",
                    "changed_at": "Когда",
                }),
                width="stretch", hide_index=True, height=min(260, 45 + 35 * len(history)),
            )

    render_asset_gallery(collect_related_images(selected_row, project_id=project_id))

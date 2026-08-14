from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.analysis_groups import WORK_GROUP_COLUMN
from petrolab.dataframe_utils import display_value, row_identity
from petrolab.db import META_COLUMNS
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
    render_asset_gallery(collect_related_images(selected_row, project_id=project_id))

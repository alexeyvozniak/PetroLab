from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import apply_quick_filter
from petrolab.db import list_change_log
from petrolab.ui.layout import render_badges, render_page_header


def render_change_log_page() -> None:
    render_page_header(
        "История правок данных",
        "Аудит ручных изменений аналитических значений и их записи обратно в связанный источник.",
        eyebrow="Система",
    )
    rows = list_change_log(limit=2000)
    if not rows:
        st.caption("Правок данных пока нет.")
        return
    dataframe = pd.DataFrame(rows)
    query = st.text_input("Поиск", placeholder="Набор, колонка, analysis ID, старое или новое значение")
    shown = apply_quick_filter(dataframe, query)
    synced = int(pd.to_numeric(shown.get("synced_to_source"), errors="coerce").fillna(0).sum()) if "synced_to_source" in shown else 0
    render_badges([
        (f"{len(shown)} записей", "neutral"),
        (f"{synced} синхронизировано с источником", "success" if synced else "neutral"),
    ])
    st.dataframe(shown, width="stretch", hide_index=True, height=700)

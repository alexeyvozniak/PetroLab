from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_change_log


def render_change_log_page() -> None:
    st.title("Журнал изменений")
    rows = list_change_log(limit=2000)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=700)
    else:
        st.caption("Изменений пока нет.")

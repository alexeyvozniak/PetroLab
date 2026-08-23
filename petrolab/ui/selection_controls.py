from __future__ import annotations

import streamlit as st

from petrolab.selections import save_selection


def render_save_selection(project_id: int | None, analysis_ids: list[str], *, key_prefix: str, context: dict | None = None) -> None:
    """Expose the same non-destructive Selection action on every linked view."""
    if project_id is None or not analysis_ids:
        return
    with st.expander("Сохранить как рабочую выборку", expanded=False):
        name = st.text_input("Название", placeholder="Например, точки для Figure 4", key=f"{key_prefix}_selection_name")
        note = st.text_input("Заметка", key=f"{key_prefix}_selection_note")
        if st.button("Сохранить Selection", disabled=not name.strip(), key=f"{key_prefix}_selection_save"):
            try:
                save_selection(int(project_id), name=name, analysis_ids=analysis_ids, note=note, context=context)
            except Exception as exc:
                st.error(f"Выборка не сохранена: {exc}")
            else:
                st.session_state["active_selection_analysis_ids"] = list(dict.fromkeys(str(value) for value in analysis_ids))
                st.session_state["active_selection_name"] = name.strip()
                st.success(f"Сохранена рабочая выборка: {len(analysis_ids)} точек.")

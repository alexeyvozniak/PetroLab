from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.db import list_projects
from petrolab.services.image_service import related_images_for_row


_ACTIVE_PROJECT_KEY = "active_project_id"


def _sync_active_project(widget_key: str) -> None:
    value = st.session_state.get(widget_key)
    if value is not None:
        st.session_state[_ACTIVE_PROJECT_KEY] = int(value)


def render_project_selector(key: str = "project_select") -> dict | None:
    """Render one page-local widget backed by a global active-project context."""
    projects = list_projects()
    if not projects:
        st.info("Создайте первый проект.")
        return None

    by_id = {int(project["id"]): project for project in projects}
    ids = list(by_id)
    active = st.session_state.get(_ACTIVE_PROJECT_KEY)
    try:
        active_id = int(active)
    except (TypeError, ValueError):
        active_id = ids[0]
    if active_id not in by_id:
        active_id = ids[0]
    st.session_state[_ACTIVE_PROJECT_KEY] = active_id

    if st.session_state.get(key) != active_id:
        st.session_state[key] = active_id

    selected_id = st.selectbox(
        "Текущий проект",
        ids,
        key=key,
        format_func=lambda project_id: str(by_id[int(project_id)]["name"]),
        on_change=_sync_active_project,
        args=(key,),
    )
    selected_id = int(selected_id)
    st.session_state[_ACTIVE_PROJECT_KEY] = selected_id
    return by_id[selected_id]


def collect_related_images(selected_row: pd.Series, project_id: int | None = None) -> list[dict]:
    return related_images_for_row(selected_row, project_id=project_id)


def render_asset_gallery(
    assets: list[dict],
    max_items: int = 20,
    width: int | str = "stretch",
) -> None:
    """Render stored images and make broken analytical links explicit."""
    if not assets:
        st.caption("Связанных изображений нет.")
        return
    if len(assets) > max_items:
        st.caption(f"Показано {max_items} из {len(assets)} изображений.")
    effective_width: int | str = "stretch" if isinstance(width, int) and width > 700 else width
    for asset in assets[:max_items]:
        if str(asset.get("link_status") or "") == "detached":
            st.warning(
                "Привязка изображения требует восстановления. "
                + str(asset.get("link_status_reason") or "Связанная аналитическая сущность больше не найдена.")
            )
        path = Path(asset["stored_path"])
        if not path.exists():
            st.warning(f"Файл изображения не найден: {asset['original_filename']}")
            continue
        try:
            st.image(
                str(path),
                caption=asset["title"] or asset["original_filename"],
                width=effective_width,
            )
        except Exception:
            st.caption(asset["original_filename"])

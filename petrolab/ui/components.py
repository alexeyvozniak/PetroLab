from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.services.image_service import related_images_for_row
from petrolab.ui.project_context import ACTIVE_PROJECT_KEY, active_project, set_active_project


def _sync_active_project(widget_key: str) -> None:
    value = st.session_state.get(widget_key)
    if value is not None:
        set_active_project(int(value))


def render_project_selector(key: str = "project_select") -> dict | None:
    """Return the global project context; render a selector only outside the normal app shell."""
    project = active_project()
    if project is None:
        st.info("Создайте первый проект.")
        return None

    if st.session_state.get("_sidebar_project_ready"):
        return project

    # Compatibility fallback for standalone page/AppTest rendering without the sidebar shell.
    from petrolab.db import list_projects

    projects = list_projects()
    by_id = {int(item["id"]): item for item in projects}
    ids = list(by_id)
    active_id = int(st.session_state.get(ACTIVE_PROJECT_KEY, int(project["id"])))
    if active_id not in by_id:
        active_id = ids[0]
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
    set_active_project(int(selected_id))
    return by_id[int(selected_id)]


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

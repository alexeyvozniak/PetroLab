from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.db import list_projects
from petrolab.services.image_service import related_images_for_row


def render_project_selector(key: str = "project_select") -> dict | None:
    """Render the shared current-project selector and return the selected project."""
    projects = list_projects()
    if not projects:
        st.info("Создайте первый проект.")
        return None
    mapping = {project["name"]: project for project in projects}
    selected_name = st.selectbox("Текущий проект", list(mapping), key=key)
    return mapping[selected_name]


def collect_related_images(selected_row: pd.Series, project_id: int | None = None) -> list[dict]:
    """UI-friendly wrapper around the image service relation resolver."""
    return related_images_for_row(selected_row, project_id=project_id)


def render_asset_gallery(
    assets: list[dict],
    max_items: int = 20,
    width: int | str = "stretch",
) -> None:
    """Render stored images responsively while tolerating missing/unreadable files."""
    if not assets:
        st.caption("Связанных изображений нет.")
        return
    # Legacy callers may still request a large pixel width. Convert it to responsive
    # layout instead of letting individual pages make different mobile decisions.
    effective_width: int | str = "stretch" if isinstance(width, int) and width > 700 else width
    for asset in assets[:max_items]:
        path = Path(asset["stored_path"])
        if not path.exists():
            st.caption(f"Файл изображения не найден: {asset['original_filename']}")
            continue
        try:
            st.image(
                str(path),
                caption=asset["title"] or asset["original_filename"],
                width=effective_width,
            )
        except Exception:
            st.caption(asset["original_filename"])

from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.db import list_image_assets, list_projects


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
    """Return images linked directly or indirectly to an analysis row."""
    assets = list_image_assets(
        project_id=project_id,
        dataset_id=int(selected_row.get("_dataset_id")),
    )
    related: list[dict] = []
    analysis_id = str(selected_row.get("_analysis_id"))
    for asset in assets:
        if asset.get("analysis_id") == analysis_id:
            related.append(asset)
        elif asset.get("scope_type") == "Набор данных":
            related.append(asset)
        elif asset.get("scope_type") == "Значение поля":
            column = asset.get("scope_column")
            if column in selected_row.index and str(selected_row.get(column)) == str(asset.get("scope_value")):
                related.append(asset)
    return related


def render_asset_gallery(assets: list[dict], max_items: int = 20, width: int = 650) -> None:
    """Render stored image assets while tolerating missing or unreadable files."""
    if not assets:
        st.caption("Связанных изображений нет.")
        return
    for asset in assets[:max_items]:
        path = Path(asset["stored_path"])
        if not path.exists():
            st.caption(f"Файл изображения не найден: {asset['original_filename']}")
            continue
        try:
            st.image(
                str(path),
                caption=asset["title"] or asset["original_filename"],
                width=width,
            )
        except Exception:
            st.caption(asset["original_filename"])

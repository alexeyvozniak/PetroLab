from __future__ import annotations

import streamlit as st

from petrolab.ui import universal_intake_extensions
from petrolab.ui.intake_workflow import _IMAGE_TYPES, _reset_transient_state_on_project_change, render_recent_import_undo
from petrolab.ui.layout import render_hint


_UPLOAD_KEY = "universal_intake_files_images"


def _existing_upload_count() -> int:
    raw = st.session_state.get(_UPLOAD_KEY)
    if isinstance(raw, (list, tuple)):
        return len(raw)
    return 1 if raw else 0


def render_simple_image_intake(project_id: int) -> None:
    """Images-only path: upload -> source sheet -> points, with no generic intake chrome."""
    _reset_transient_state_on_project_change(int(project_id))
    existing_count = _existing_upload_count()

    if existing_count:
        with st.expander(f"Файлы · {existing_count} · добавить / убрать", expanded=False):
            uploads = st.file_uploader(
                "Изображения",
                type=_IMAGE_TYPES,
                accept_multiple_files=True,
                key=_UPLOAD_KEY,
            )
    else:
        uploads = st.file_uploader(
            "Перетащите изображения или выберите файлы",
            type=_IMAGE_TYPES,
            accept_multiple_files=True,
            key=_UPLOAD_KEY,
        )

    if not uploads:
        render_hint(
            "Можно выбрать сразу много PPL, XPL, BSE и карт. После загрузки PetroLab покажет фотографии по одной: "
            "исходный лист → точки → следующая фотография."
        )
        render_recent_import_undo(int(project_id))
        return

    images = [(upload.name, upload.getvalue()) for upload in uploads]
    universal_intake_extensions.render_image_wizard_multi_dataset(
        int(project_id), images, []
    )
    render_recent_import_undo(int(project_id))

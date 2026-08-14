from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import ensure_session_schema
from petrolab.collaboration_merge import apply_collaboration_merge, plan_collaboration_merge
from petrolab.generations import ensure_generation_storage
from petrolab.sample_registry import list_samples
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


def render_collaboration_page() -> None:
    render_page_header(
        "Объединить проект коллеги",
        "Импортируйте переносимый .petrolab-пакет в текущий проект. PetroLab сначала показывает план и никогда не склеивает похожие Sample автоматически.",
        eyebrow="Совместная работа",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите целевой проект.")
        return
    project_id = int(project_id)
    ensure_session_schema()
    ensure_generation_storage()

    uploaded = st.file_uploader("Проект коллеги (.petrolab)", type=["petrolab"], key="collab_archive")
    if uploaded is None:
        st.caption("Попросите коллегу экспортировать переносимый проект PetroLab. Для объединения достаточно самого .petrolab-файла.")
        return

    archive_bytes = uploaded.getvalue()
    with tempfile.NamedTemporaryFile(suffix=".petrolab", delete=False) as handle:
        handle.write(archive_bytes)
        temp_path = Path(handle.name)
    try:
        try:
            plan = plan_collaboration_merge(temp_path, project_id)
        except Exception as exc:
            st.error(f"Пакет не готов к объединению: {exc}")
            return

        render_badges([
            (plan.incoming_project_name, "accent"),
            (f"{plan.sample_count} Sample", "neutral"),
            (f"{plan.dataset_count} datasets", "neutral"),
            (f"{plan.analysis_count} анализов", "neutral"),
            (f"{plan.rock_count} пород", "neutral"),
            (f"{plan.study_count} источников", "neutral"),
        ])
        st.subheader("1 · Сопоставьте образцы")
        st.caption("Похожее написание — только подсказка. Каждый входящий Sample требует явного решения.")
        target_samples = list_samples(project_id)
        target_by_id = {int(row["id"]): row for row in target_samples}
        decisions: dict[int, int | None] = {}
        rows = []
        for item in plan.samples:
            likely = [target_by_id[sid]["name"] for sid in item.suggested_target_ids if sid in target_by_id]
            rows.append({"Входящий Sample": item.name, "Похожие в проекте": ", ".join(likely) or "—"})
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        for item in plan.samples:
            options = [-1] + list(target_by_id)
            suggested = item.suggested_target_ids[0] if len(item.suggested_target_ids) == 1 else -1
            index = options.index(suggested) if suggested in options else 0
            choice = st.selectbox(
                f"{item.name}", options, index=index,
                format_func=lambda value: "Создать новый Sample" if value == -1 else f"Использовать: {target_by_id[int(value)]['name']}",
                key=f"collab_sample_{plan.archive_sha256}_{item.source_sample_id}",
                help="PetroLab никогда не объединяет Sample только из-за похожего названия.",
            )
            decisions[item.source_sample_id] = None if int(choice) == -1 else int(choice)

        st.subheader("2 · Проверка")
        st.info("Будут перенесены научные данные и provenance с новыми внутренними ID. Настройки интерфейса, change-log и пересчитываемые derived-результаты не объединяются.")
        confirm = st.checkbox(
            "Я проверил сопоставление Sample и хочу добавить проект коллеги в текущий проект",
            key=f"collab_confirm_{plan.archive_sha256}",
        )
        if st.button("Объединить проекты", type="primary", disabled=not confirm, key=f"collab_apply_{plan.archive_sha256}"):
            try:
                result = apply_collaboration_merge(temp_path, project_id, decisions)
                st.success(
                    f"Добавлен проект «{result.imported_project_name}»: {result.sample_count} Sample, "
                    f"{result.dataset_count} datasets, {result.analysis_count} анализов, "
                    f"{result.rock_count} записей пород, {result.study_count} источников."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Объединение отменено без частичного импорта: {exc}")
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

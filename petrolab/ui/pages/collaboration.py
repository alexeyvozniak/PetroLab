from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import ensure_session_schema
from petrolab.collaboration_merge import apply_collaboration_merge, plan_collaboration_merge
from petrolab.collaboration_targeting import (
    preferred_project_id,
    read_archive_context_hint,
    suggested_project_ids,
)
from petrolab.db import list_projects
from petrolab.generations import ensure_generation_storage
from petrolab.sample_registry import list_samples
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


def render_collaboration_page() -> None:
    render_page_header(
        "Добавить данные коллеги",
        "Импортируйте полный проект или маленький .petrolab-фрагмент. PetroLab сначала предложит, "
        "в какой существующий проект добавить данные, а затем отдельно проверит каждый Sample.",
        eyebrow="Совместная работа",
    )

    uploaded = st.file_uploader(
        "Проект или фрагмент (.petrolab)", type=["petrolab"], key="collab_archive"
    )
    if uploaded is None:
        st.caption(
            "Коллега может прислать весь проект или только один Sample/шлиф с выбранными EDS и LA-ICP-MS точками."
        )
        return

    archive_bytes = uploaded.getvalue()
    with tempfile.NamedTemporaryFile(suffix=".petrolab", delete=False) as handle:
        handle.write(archive_bytes)
        temp_path = Path(handle.name)
    try:
        try:
            incoming_name, _payload_hint = read_archive_context_hint(temp_path)
        except Exception as exc:
            st.error(f"Не удалось прочитать пакет: {exc}")
            return

        projects = list_projects()
        if not projects:
            st.info(
                f"В пакете указан контекст «{incoming_name}», но в этой базе пока нет рабочих проектов. "
                "Сначала создайте проект, в который нужно добавить данные."
            )
            return

        project_by_id = {int(project["id"]): project for project in projects}
        matches = suggested_project_ids(projects, incoming_name)
        preferred = preferred_project_id(
            projects,
            incoming_name,
            active_project_id=active_project_id(),
        )
        if len(matches) == 1:
            matched_name = str(project_by_id[int(matches[0])]["name"])
            st.info(
                f"Похоже, пакет относится к уже существующему проекту «{matched_name}». "
                "Можно добавить новые Sample туда; ничего не объединится без вашего подтверждения."
            )
        elif len(matches) > 1:
            st.warning(
                f"Для контекста «{incoming_name}» найдено несколько похожих проектов. "
                "Выберите целевой проект вручную."
            )
        else:
            st.caption(
                f"Входящий проектный контекст: «{incoming_name}». Выберите, куда добавить эти данные."
            )

        project_ids = list(project_by_id)
        preferred_index = project_ids.index(int(preferred)) if preferred in project_ids else 0
        project_id = int(
            st.selectbox(
                "Куда добавить пакет?",
                project_ids,
                index=preferred_index,
                format_func=lambda value: str(project_by_id[int(value)]["name"]),
                key=f"collab_target_project_{uploaded.name}",
                help=(
                    "Совпадение названия — только подсказка. Вы сами выбираете проект назначения, "
                    "а на следующем шаге отдельно решаете судьбу каждого Sample."
                ),
            )
        )
        if len(matches) == 1 and project_id == int(matches[0]):
            st.caption(
                "Новые образцы будут добавлены в этот проект; совпадающие Sample можно явно связать "
                "с уже существующими, а остальные создать как новые."
            )

        ensure_session_schema()
        ensure_generation_storage()
        try:
            plan = plan_collaboration_merge(temp_path, project_id)
        except Exception as exc:
            st.error(f"Пакет не готов к объединению: {exc}")
            return

        kind_label = "Фрагмент" if plan.payload_kind == "fragment" else "Проект"
        badges = [
            (kind_label, "accent"),
            (plan.incoming_project_name, "neutral"),
            (f"{plan.sample_count} Sample", "neutral"),
            (f"{plan.dataset_count} datasets", "neutral"),
            (f"{plan.analysis_count} анализов", "neutral"),
        ]
        if plan.entity_count:
            badges.append((f"{plan.entity_count} физ. объектов", "neutral"))
        if plan.observation_count:
            badges.append((f"{plan.observation_count} наблюдений", "neutral"))
        if plan.rock_count:
            badges.append((f"{plan.rock_count} пород", "neutral"))
        if plan.study_count:
            badges.append((f"{plan.study_count} источников", "neutral"))
        render_badges(badges)

        st.subheader("1 · Сопоставьте образцы")
        st.caption(
            "Похожее написание — только подсказка. Каждый входящий Sample требует явного решения: "
            "создать новый или использовать уже существующий."
        )
        target_samples = list_samples(project_id)
        target_by_id = {int(row["id"]): row for row in target_samples}
        decisions: dict[int, int | None] = {}
        rows = []
        for item in plan.samples:
            likely = [
                target_by_id[sid]["name"]
                for sid in item.suggested_target_ids
                if sid in target_by_id
            ]
            rows.append(
                {
                    "Входящий Sample": item.name,
                    "Похожие в проекте": ", ".join(likely) or "—",
                }
            )
        if rows:
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        for item in plan.samples:
            options = [-1] + list(target_by_id)
            suggested = item.suggested_target_ids[0] if len(item.suggested_target_ids) == 1 else -1
            index = options.index(suggested) if suggested in options else 0
            choice = st.selectbox(
                f"{item.name}",
                options,
                index=index,
                format_func=lambda value: (
                    "Создать новый Sample"
                    if value == -1
                    else f"Использовать: {target_by_id[int(value)]['name']}"
                ),
                key=f"collab_sample_{plan.archive_sha256}_{item.source_sample_id}",
                help="PetroLab никогда не объединяет Sample только из-за похожего названия.",
            )
            decisions[item.source_sample_id] = None if int(choice) == -1 else int(choice)

        st.subheader("2 · Проверка")
        if plan.payload_kind == "fragment":
            st.info(
                "Будут добавлены только данные, реально лежащие во фрагменте: выбранные шлифы/точки, "
                "их наблюдения, связанные анализы, сессии и изображения. Остальная база отправителя не переносится."
            )
        else:
            st.info(
                "Будут перенесены научные данные и provenance с новыми внутренними ID. Настройки интерфейса, "
                "change-log и пересчитываемые derived-результаты не объединяются."
            )
        confirm = st.checkbox(
            f"Я проверил Sample и хочу добавить этот пакет в «{project_by_id[project_id]['name']}»",
            key=f"collab_confirm_{plan.archive_sha256}_{project_id}",
        )
        if st.button(
            "Добавить данные",
            type="primary",
            disabled=not confirm,
            key=f"collab_apply_{plan.archive_sha256}_{project_id}",
        ):
            try:
                result = apply_collaboration_merge(temp_path, project_id, decisions)
                st.session_state["active_project_id"] = project_id
                st.session_state["sidebar_project"] = project_id
                extra = ""
                if result.entity_count or result.observation_count:
                    extra = (
                        f", {result.entity_count} физических объектов, "
                        f"{result.observation_count} наблюдений"
                    )
                st.success(
                    f"Добавлен {kind_label.lower()} «{result.imported_project_name}»: "
                    f"{result.sample_count} Sample, {result.dataset_count} datasets, "
                    f"{result.analysis_count} анализов{extra}."
                )
                st.rerun()
            except Exception as exc:
                st.error(f"Объединение отменено без частичного импорта: {exc}")
    finally:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass

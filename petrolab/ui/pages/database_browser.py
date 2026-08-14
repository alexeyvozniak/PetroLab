from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.sample_locations import (
    current_entity_location,
    current_sample_location,
    entity_location_history,
    record_entity_location,
    record_sample_location,
    sample_location_history,
)
from petrolab.sample_registry import (
    add_sample_alias,
    create_sample,
    find_sample_matches,
    link_rock_record_to_sample,
    list_samples,
)
from petrolab.db import link_dataset_to_project, list_accessible_datasets, list_datasets
from petrolab.analysis_groups import attach_work_groups
from petrolab.measurement_registry import list_entities
from petrolab.derived import load_unified_with_derived
from petrolab.generations import attach_generations
from petrolab.unified_catalog import mineral_inventory, sample_overview, unlinked_rock_samples, whole_rock_inventory
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.settings_service import load_settings, save_settings
from petrolab.source_registry import (
    SOURCE_LABEL_COLUMN,
    SOURCE_TABLE_COLUMN,
    attach_study_metadata,
)


_SELECTION_FIELDS = {
    "Object": ("Object", "Объект", "Locality", "Местность"),
    "Sample": ("Sample", "Образец"),
    "Mineral": ("Минерал", "Mineral"),
    "Generation": ("Generation", "Генерация"),
    "Method": ("Method", "Метод", "Technique", "Метод анализа"),
    "Source": ("Источник / статья", (SOURCE_LABEL_COLUMN,)),
}


def _first_column(dataframe: pd.DataFrame, names: tuple[str, ...]) -> str | None:
    lowered = {str(column).casefold(): str(column) for column in dataframe.columns}
    for name in names:
        column = lowered.get(name.casefold())
        if column:
            return column
    return None


def _render_selection_toolbar(project_id: int, scope: str, query: str) -> None:
    """Persist one explicit row selection for plots, tables and safe Excel edits."""
    datasets = list_accessible_datasets(project_id) if scope == "Активный проект" else list_datasets()
    dataset_ids = [int(dataset["id"]) for dataset in datasets]
    if not dataset_ids:
        return
    dataframe = attach_study_metadata(
        attach_generations(attach_work_groups(load_unified_with_derived(None, dataset_ids)))
    )
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    # Object/locality is optional for imported chemistry.  When it has been
    # entered in the canonical Sample registry, expose it as an ordinary
    # filterable field without duplicating it into every raw Excel row.
    if scope == "Активный проект" and "Sample" in dataframe.columns and "Object" not in dataframe.columns:
        object_by_sample = {
            str(row["name"]): str(row.get("locality") or "")
            for row in list_samples(project_id)
            if str(row.get("locality") or "").strip()
        }
        if object_by_sample:
            dataframe["Object"] = dataframe["Sample"].astype(str).map(object_by_sample).fillna("")

    with st.container(border=True):
        st.markdown("#### Текущий отбор")
        st.caption(
            "Поиск и фильтры работают по строкам анализов. Этот же точный отбор можно передать "
            "в график, supplementary-таблицу или редактор исходного Excel."
        )
        filtered = dataframe.copy()
        if query.strip():
            text = query.strip()
            filtered = filtered.loc[
                filtered.astype(str).apply(
                    lambda column: column.str.contains(text, case=False, na=False)
                ).any(axis=1)
            ].copy()

        active_filters: dict[str, list[str]] = {}
        filter_items = list(_SELECTION_FIELDS.items())
        for row_start in range(0, len(filter_items), 3):
            row_items = filter_items[row_start:row_start + 3]
            columns = st.columns(len(row_items))
            for widget, (field_key, (label, candidates)) in zip(columns, row_items):
                column = _first_column(filtered, candidates)
                if column is None:
                    widget.caption(f"{label}: нет поля")
                    continue
                values = sorted(filtered[column].dropna().astype(str).loc[lambda value: value.str.strip().ne("")].unique())
                selected = widget.multiselect(label, values, key=f"db_selection_{field_key}")
                if selected:
                    filtered = filtered[filtered[column].astype(str).isin(selected)].copy()
                    active_filters[label] = selected

        analysis_ids = filtered["_analysis_id"].astype(str).tolist()
        selected_dataset_ids = sorted({int(value) for value in filtered["_dataset_id"].dropna().tolist()})
        selected_study_ids = sorted({int(value) for value in filtered.get("_study_id", pd.Series(dtype="Int64")).dropna().tolist()})
        render_badges([
            (f"{len(analysis_ids):,} точек".replace(",", " "), "accent"),
            (f"{len(selected_dataset_ids)} наборов", "neutral"),
            (f"{len(selected_study_ids)} источников", "neutral"),
        ])
        visible = [
            column for column in [
                "Sample", "Grain", "Point", "Минерал", "Generation", "Method",
                SOURCE_LABEL_COLUMN, SOURCE_TABLE_COLUMN, "QC уровень", "QC решение", "Набор",
            ]
            if column in filtered.columns
        ]
        st.dataframe(filtered[visible].head(250), width="stretch", hide_index=True, height=230)
        if len(filtered) > 250:
            st.caption("Показаны первые 250 строк; действия ниже применяются ко всем точкам отбора.")

        plot, table, excel = st.columns(3)
        context = {
            "dataset_ids": selected_dataset_ids,
            "study_ids": selected_study_ids,
            "analysis_ids": analysis_ids,
            "filters": active_filters,
            "query": query.strip(),
            "scope": scope,
        }
        if plot.button("Построить график по текущему отбору", type="primary", disabled=not analysis_ids, width="stretch"):
            st.session_state["workflow_plot_dataset_ids"] = selected_dataset_ids
            st.session_state["workflow_plot_analysis_ids"] = analysis_ids
            st.session_state["workflow_plot_context"] = context
            st.session_state["workflow_plot_notice"] = "В график передан текущий отбор базы."
            navigate("plots")
            st.rerun()
        if table.button("Таблица статьи из этого отбора", disabled=not analysis_ids, width="stretch"):
            st.session_state["workflow_table_dataset_ids"] = selected_dataset_ids
            st.session_state["workflow_table_analysis_ids"] = analysis_ids
            st.session_state["workflow_table_context"] = context
            navigate("article_tables")
            st.rerun()
        if excel.button("Открыть отбор для сохранения в исходный Excel", disabled=not analysis_ids, width="stretch"):
            st.session_state["workflow_edit_dataset_ids"] = selected_dataset_ids
            st.session_state["workflow_edit_analysis_ids"] = analysis_ids
            st.session_state["workflow_edit_context"] = context
            navigate("analyses")
            st.rerun()


def _batch_field_samples(project_id: int) -> None:
    with st.expander("Добавить полевые образцы", expanded=False):
        st.caption("Можно внести образцы ещё до появления XRF, зонда, лазера или изотопии. Один образец — одна строка.")
        text = st.text_area(
            "Названия образцов",
            key="db_browser_batch_samples",
            placeholder="KV-01\nKV-02\nKV-03",
            height=130,
        )
        field_lithology = st.text_input("Общее полевое название · необязательно", key="db_browser_field_lithology")
        locality = st.text_input("Местность · необязательно", key="db_browser_locality")
        if st.button("Проверить и добавить", disabled=not text.strip(), key="db_browser_add_samples"):
            names = list(dict.fromkeys(line.strip() for line in text.splitlines() if line.strip()))
            conflicts = []
            created = 0
            for name in names:
                matches = find_sample_matches(project_id, name)
                if matches:
                    conflicts.append((name, matches[0].canonical_name, matches[0].match_kind))
                    continue
                create_sample(project_id, name, field_lithology=field_lithology, locality=locality)
                created += 1
            if created:
                st.success(f"Добавлено образцов: {created}.")
            if conflicts:
                st.warning("Похожие образцы не были созданы автоматически. Проверьте совпадения ниже.")
                st.dataframe(pd.DataFrame(conflicts, columns=["Введено", "Похоже на", "Причина"]), width="stretch", hide_index=True)


def _duplicate_guard(project_id: int) -> None:
    with st.expander("Проверить название образца / alias", expanded=False):
        proposed = st.text_input("Название", key="db_browser_duplicate_name", placeholder="например, PG_15")
        if proposed:
            matches = find_sample_matches(project_id, proposed)
            if not matches:
                st.success("Похожих образцов в активном проекте не найдено.")
            else:
                rows = [{"Образец": m.canonical_name, "Совпало как": m.matched_name, "Тип": m.match_kind, "sample_id": m.sample_id} for m in matches]
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
                sample_ids = [m.sample_id for m in matches]
                selected = st.selectbox("Считать это alias существующего образца", sample_ids, format_func=lambda sid: next(m.canonical_name for m in matches if m.sample_id == sid), key="db_browser_alias_target")
                if st.button("Добавить alias", key="db_browser_add_alias"):
                    add_sample_alias(int(selected), proposed, source="user_confirmed")
                    st.success("Alias сохранён. Следующие импорты смогут распознавать это написание.")


def _link_legacy_rocks(project_id: int) -> None:
    unlinked = unlinked_rock_samples(project_id)
    if unlinked.empty:
        return
    with st.expander(f"Связать старые whole-rock записи с Sample · {len(unlinked)}", expanded=False):
        st.caption("Старые записи пород пока могут жить отдельно от универсального Sample. Здесь их можно связать без потери исходных данных.")
        samples = list_samples(project_id)
        if not samples:
            st.info("Сначала создайте хотя бы один Sample.")
            return
        rock_map = {f"{row['name']} · {row.get('lithology','')} · id {int(row['rock_id'])}": int(row["rock_id"]) for _, row in unlinked.iterrows()}
        sample_map = {f"{row['name']} · id {int(row['id'])}": int(row["id"]) for row in samples}
        rock_label = st.selectbox("Whole-rock запись", list(rock_map), key="db_browser_rock_link")
        sample_label = st.selectbox("Sample", list(sample_map), key="db_browser_sample_link")
        if st.button("Связать", key="db_browser_link_rock"):
            link_rock_record_to_sample(rock_map[rock_label], sample_map[sample_label])
            st.success("Связь сохранена.")


def _link_library_datasets(project_id: int) -> None:
    """Let an article project reuse a library/other-project dataset by reference."""
    accessible = {int(item["id"]) for item in list_accessible_datasets(project_id)}
    candidates = [item for item in list_datasets() if int(item["id"]) not in accessible]
    if not candidates:
        return
    with st.expander("Подключить данные из общей базы", expanded=False):
        st.caption(
            "Набор остаётся в исходном проекте или «Общей библиотеке». Здесь создаётся только ссылка для отбора и графиков — без копирования химии."
        )
        labels = {
            f"{item['project_name']} · {item['name']} · {int(item['row_count'])} строк": int(item["id"])
            for item in candidates
        }
        selected = st.multiselect("Наборы для текущего проекта", list(labels), key="db_browser_library_links")
        note = st.text_input("Зачем подключён набор · необязательно", key="db_browser_library_note")
        if st.button("Подключить выбранные наборы", disabled=not selected, key="db_browser_link_library"):
            for label in selected:
                link_dataset_to_project(project_id, labels[label], note)
            st.success(f"Подключено наборов: {len(selected)}. Они доступны в экране графиков.")
            st.rerun()
        if accessible:
            st.caption(f"Наборов в рабочем контексте: {len(accessible)}.")


def _render_sample_location_card(project_id: int) -> None:
    """A voluntary specimen passport: current place plus immutable movement history."""
    samples = list_samples(project_id)
    if not samples:
        return
    settings = load_settings()
    remind = bool(settings.get("show_sample_location_prompt", True))
    with st.expander("Карточка образца и местонахождение", expanded=remind):
        if remind:
            st.markdown("#### Где сейчас образец?")
            st.caption(
                "Необязательная короткая отметка для физических образцов и шлифов. "
                "Она не мешает сохранению данных; бывшие места останутся в истории."
            )
        labels = {
            f"{row['name']} · id {int(row['id'])}": int(row["id"])
            for row in samples
        }
        selected_label = st.selectbox("Образец", list(labels), key="sample_location_selected")
        sample_id = labels[selected_label]
        targets: dict[str, tuple[str, int]] = {f"Образец · {selected_label}": ("sample", sample_id)}
        for entity in list_entities(project_id, sample_id=sample_id):
            if str(entity.get("kind")) != "thin_section":
                continue
            targets[f"Шлиф / препарат · {entity['name']}"] = ("entity", int(entity["id"]))
        target_label = st.selectbox("Что сейчас находится в пути или на хранении?", list(targets), key=f"sample_location_target_{sample_id}")
        target_kind, target_id = targets[target_label]
        current = (
            current_sample_location(target_id)
            if target_kind == "sample"
            else current_entity_location(target_id)
        )
        if current:
            st.info(f"Сейчас: **{current.location}** · отмечено {current.recorded_at}")
        else:
            st.info("Текущее местонахождение ещё не отмечено.")
        location = st.text_input(
            "Где сейчас находится выбранный образец / шлиф?",
            value=current.location if current else "",
            placeholder="например, шкаф A-3; у Ивана; лаборатория МГУ",
            key=f"sample_location_value_{target_kind}_{target_id}",
        )
        note = st.text_input(
            "Комментарий · необязательно",
            value="",
            placeholder="выдан на анализ; коробка; дата возврата",
            key=f"sample_location_note_{target_kind}_{target_id}",
        )
        c1, c2 = st.columns(2)
        never_ask = c2.checkbox(
            "Больше не показывать напоминание",
            value=False,
            key=f"sample_location_hide_prompt_{sample_id}",
        )
        if c1.button("Обновить местонахождение", type="primary", key=f"sample_location_save_{sample_id}"):
            try:
                event = (
                    record_sample_location(target_id, location, note=note)
                    if target_kind == "sample"
                    else record_entity_location(target_id, location, note=note)
                )
            except (KeyError, ValueError) as exc:
                st.error(str(exc))
            else:
                if never_ask:
                    save_settings({**settings, "show_sample_location_prompt": False})
                st.success(f"Отмечено: {event.location}.")
                st.rerun()
        if never_ask and c2.button("Скрыть напоминание", key=f"sample_location_hide_{sample_id}"):
            save_settings({**settings, "show_sample_location_prompt": False})
            st.success("Напоминание скрыто. Карточка и история остаются доступны здесь.")
            st.rerun()

        history = (
            sample_location_history(target_id)
            if target_kind == "sample"
            else entity_location_history(target_id)
        )
        if history:
            st.caption("История перемещений")
            st.dataframe(
                pd.DataFrame(history).rename(columns={
                    "location": "Место",
                    "note": "Комментарий",
                    "recorded_at": "Отмечено",
                }),
                width="stretch", hide_index=True, height=min(280, 44 + 34 * len(history)),
            )


def render_database_browser_page() -> None:
    render_page_header(
        "Вся база",
        "Единый каталог образцов и всех связанных с ними минералов, whole-rock данных, изотопии и будущих аналитических сессий.",
        eyebrow="База данных",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите проект.")
        return
    project_id = int(project_id)

    c1, c2 = st.columns(2)
    scope = c1.segmented_control("Область", ["Активный проект", "Все проекты"], default="Активный проект", key="db_browser_scope")
    query = c2.text_input("Поиск", key="db_browser_search", placeholder="образец, зерно, точка, минерал, местность…")
    scope_project = project_id if scope == "Активный проект" else None

    _render_selection_toolbar(project_id, scope, query)

    overview = sample_overview(scope_project)
    inventory = mineral_inventory(scope_project)
    rocks = whole_rock_inventory(scope_project)
    render_badges([
        (f"{len(overview)} образцов", "accent"),
        (f"{int(overview['Минеральных анализов'].sum()) if not overview.empty else 0} минеральных анализов", "neutral"),
        (f"{int(overview['Изотопных измерений'].sum()) if not overview.empty else 0} изотопных измерений", "neutral"),
    ])

    tab_samples, tab_minerals, tab_rocks, tab_tools = st.tabs(["Образцы", "Минералы", "Породы и изотопы", "Порядок в базе"])
    with tab_samples:
        view = overview.copy()
        if query.strip() and not view.empty:
            mask = view.astype(str).apply(lambda col: col.str.contains(query.strip(), case=False, na=False)).any(axis=1)
            view = view[mask]
        st.dataframe(view, width="stretch", hide_index=True, height=560)
        _render_sample_location_card(project_id)
        empty_count = int(view["Пустой"].sum()) if not view.empty and "Пустой" in view.columns else 0
        if empty_count:
            st.caption(f"Пустых полевых образцов без аналитики: {empty_count}. Это нормально: они уже являются полноценными Sample и могут пополняться позже.")

    with tab_minerals:
        st.caption("Это глобальный индекс по mineral_key. Например, nepheline можно собрать из всех datasets и проектов независимо от исходных Excel.")
        st.dataframe(inventory, width="stretch", hide_index=True, height=520)

    with tab_rocks:
        st.dataframe(rocks, width="stretch", hide_index=True, height=520)

    with tab_tools:
        _batch_field_samples(project_id)
        _duplicate_guard(project_id)
        _link_legacy_rocks(project_id)
        _link_library_datasets(project_id)

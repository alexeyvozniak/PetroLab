from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.sample_registry import (
    add_sample_alias,
    create_sample,
    find_sample_matches,
    link_rock_record_to_sample,
    list_samples,
)
from petrolab.unified_catalog import mineral_inventory, sample_overview, unlinked_rock_samples, whole_rock_inventory
from petrolab.ui.layout import render_badges, render_page_header
from petrolab.ui.project_context import active_project_id


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
            st.rerun()


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
    query = c2.text_input("Поиск", key="db_browser_search", placeholder="образец, проект, минерал, местность…")
    scope_project = project_id if scope == "Активный проект" else None

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

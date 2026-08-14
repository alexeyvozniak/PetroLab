from __future__ import annotations

import streamlit as st

from petrolab.project_health import ProjectHealthIssue, project_health
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


def _open_issue(issue: ProjectHealthIssue) -> None:
    if issue.dataset_id is not None:
        st.session_state["workflow_focus_dataset_id"] = int(issue.dataset_id)
        if issue.route == "mixed_minerals":
            st.session_state["workflow_mixed_dataset_id"] = int(issue.dataset_id)
        elif issue.route == "formulae":
            st.session_state["workflow_formula_dataset_id"] = int(issue.dataset_id)
    navigate(issue.route)
    st.rerun()


def _render_issue(issue: ProjectHealthIssue, index: int) -> None:
    tone = "warning" if issue.severity == "warning" else "neutral"
    with st.container(border=True):
        render_badges([(f"{issue.count:,}".replace(",", " "), tone)])
        st.markdown(f"**{issue.title}**")
        st.caption(issue.detail)
        if st.button("Разобрать", key=f"attention_{issue.kind}_{index}", width="stretch"):
            _open_issue(issue)


def render_attention_page() -> None:
    project = active_project()
    render_page_header(
        "Требует внимания",
        "PetroLab собирает оставшиеся хвосты в одном месте. Ничего из этого не блокирует просмотр исходных данных.",
        eyebrow="Рабочий процесс",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        if st.button("Проекты", type="primary", key="attention_projects"):
            navigate("projects")
            st.rerun()
        return

    health = project_health(int(project["id"]))
    score = int(health["score"])
    render_badges([
        (f"Порядок · {score}%", "success" if score >= 90 else "warning"),
        (f"важных пунктов · {health['required_count']}", "warning" if health["required_count"] else "success"),
        (f"необязательных · {health['optional_count']}", "neutral"),
    ])

    if not health["issues"]:
        st.success("Сейчас PetroLab не видит незакрытых организационных или расчётных хвостов.")
        c1, c2 = st.columns(2)
        if c1.button("Продолжить рабочий процесс", type="primary", width="stretch"):
            navigate("workflow")
            st.rerun()
        if c2.button("Добавить данные", width="stretch"):
            navigate("add_data")
            st.rerun()
        return

    render_section_header("Сначала проверить", "Это влияет на целостность контекста или актуальность derived-результатов")
    if health["required"]:
        for index, issue in enumerate(health["required"]):
            _render_issue(issue, index)
    else:
        st.success("Обязательных хвостов нет.")

    if health["optional"]:
        render_section_header("Можно дополнить позже", "Полезно для порядка, но не делает анализы неправильными")
        for index, issue in enumerate(health["optional"], start=1000):
            _render_issue(issue, index)

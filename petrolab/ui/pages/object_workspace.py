from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import human_point_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.measurement_registry import list_entities
from petrolab.repositories.image_repository import list_image_records
from petrolab.sample_registry import list_samples
from petrolab.source_registry import SOURCE_LABEL_COLUMN, attach_study_metadata
from petrolab.thermodynamics import list_thermodynamic_runs
from petrolab.thermobarometry import list_runs as list_legacy_thermobarometry_runs
from petrolab.ui.analysis_table import render_analysis_table
from petrolab.ui.components import render_asset_gallery
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.selection_context import read_selection
from petrolab.ui.work_context import set_work_context


_ID_COLUMNS = (
    "Sample", "Grain", "Point", "Generation", "PetroLab Generation", "Рабочая группа",
    "Минерал", "Mineral", "Набор", SOURCE_LABEL_COLUMN, "QC уровень", "QC решение", "Method", "Метод",
)


def _analysis_columns(dataframe: pd.DataFrame) -> list[str]:
    identity = [column for column in _ID_COLUMNS if column in dataframe.columns]
    chemistry = [
        column for column in dataframe.columns
        if not str(column).startswith("_")
        and column not in identity
        and (str(column).endswith("O") or "O2" in str(column) or "O3" in str(column) or "µg/g" in str(column) or "ppm" in str(column))
    ]
    return identity + chemistry[:14]


def _query_match(texts: list[str], query: str) -> bool:
    needle = query.strip().casefold()
    return not needle or any(needle in str(value or "").casefold() for value in texts)


def _filter_rows(dataframe: pd.DataFrame, query: str) -> pd.DataFrame:
    needle = str(query or "").strip()
    if not needle or dataframe.empty:
        return dataframe
    columns = [column for column in _ID_COLUMNS if column in dataframe.columns]
    if not columns:
        return dataframe.iloc[0:0].copy()
    mask = pd.Series(False, index=dataframe.index, dtype=bool)
    for column in columns:
        mask |= dataframe[column].astype(str).str.contains(needle, case=False, na=False, regex=False)
    return dataframe.loc[mask].copy()


def _filter_dicts(items: list[dict], query: str) -> list[dict]:
    needle = str(query or "").strip().casefold()
    if not needle:
        return items
    result: list[dict] = []
    for item in items:
        haystack = " ".join(str(value) for key, value in item.items() if not str(key).startswith("_")).casefold()
        if needle in haystack:
            result.append(item)
    return result


def _flatten_thermodynamics(project_id: int, analysis_ids: set[str]) -> pd.DataFrame:
    rows: list[dict] = []
    if not analysis_ids:
        return pd.DataFrame()
    for run in list_thermodynamic_runs(project_id):
        for result in run.results:
            if str(result.get("_analysis_id", "")) not in analysis_ids:
                continue
            row = dict(result)
            row.update({
                "Run": run.id,
                "Метод": run.method_title,
                "Режим": run.input_mode,
                "Тип": run.parameter_kind,
                "Актуальность": "Актуален" if run.is_current else "Требует пересчёта",
                "Рассчитано": run.calculated_at,
            })
            rows.append(row)
    for run in list_legacy_thermobarometry_runs(project_id):
        for result in run.results:
            if str(result.get("_analysis_id", "")) not in analysis_ids:
                continue
            row = dict(result)
            row.update({
                "Run": f"legacy-{run.id}",
                "Метод": run.method_title,
                "Режим": "single_mineral",
                "Тип": "temperature",
                "Актуальность": "Актуален" if run.is_current else "Требует пересчёта",
                "Рассчитано": run.calculated_at,
            })
            rows.append(row)
    return pd.DataFrame(rows)


def _secondary_selection_actions(dataframe: pd.DataFrame, dataset_ids: list[int]) -> None:
    context = read_selection()
    if not context.analysis_ids:
        return
    available = set(dataframe.get("_analysis_id", pd.Series(dtype=str)).astype(str))
    ids = [analysis_id for analysis_id in context.analysis_ids if analysis_id in available]
    if not ids:
        return
    render_section_header("Ещё действия", "Для текущего общего отбора")
    c1, c2, c3 = st.columns(3)
    if c1.button("Редактировать значения", width="stretch", key="workspace_selection_edit"):
        st.session_state["workflow_edit_dataset_ids"] = [int(value) for value in dataset_ids]
        st.session_state["workflow_edit_analysis_ids"] = ids
        navigate("analyses")
        st.rerun()
    if c2.button("Таблица для статьи", width="stretch", key="workspace_selection_article"):
        st.session_state["workflow_table_dataset_ids"] = [int(value) for value in dataset_ids]
        st.session_state["workflow_table_analysis_ids"] = ids
        navigate("article_tables")
        st.rerun()
    if c3.button("Термодинамика", width="stretch", key="workspace_selection_thermo"):
        st.session_state["thermodynamics_workspace_analysis_ids"] = ids
        st.session_state["thermodynamics_workspace_dataset_ids"] = [int(value) for value in dataset_ids]
        navigate("thermobarometry")
        st.rerun()


def _workspace_tabs(
    *,
    project_id: int,
    title: str,
    dataframe: pd.DataFrame,
    dataset_ids: list[int],
    images: list[dict],
    entities: list[dict],
    context_rows: list[tuple[str, str]],
    context_kind: str,
    context_label: str,
    sample: str | None = None,
    sample_id: int | None = None,
) -> None:
    full_analysis_ids = dataframe["_analysis_id"].astype(str).tolist() if "_analysis_id" in dataframe.columns else []
    set_work_context(
        project_id=project_id,
        kind=context_kind,
        label=context_label,
        dataset_ids=dataset_ids,
        analysis_ids=full_analysis_ids,
        sample=sample,
        sample_id=sample_id,
    )

    search_col, everywhere_col = st.columns([5, 1])
    with search_col:
        local_query = st.text_input(
            "Найти здесь",
            key=f"workspace_local_search_{context_kind}",
            placeholder=f"🔎 Найти в {context_label}…",
            label_visibility="collapsed",
        )
    with everywhere_col:
        if st.button("Везде", key=f"workspace_search_all_{context_kind}", width="stretch", help="Искать тот же запрос по всему проекту"):
            st.session_state["global_search_query_pending"] = str(local_query or "").strip()
            st.session_state["global_search_scope_pending"] = "all"
            navigate("search")
            st.rerun()

    working = _filter_rows(dataframe, local_query)
    visible_images = _filter_dicts(images, local_query)
    visible_entities = _filter_dicts(entities, local_query)
    analysis_ids = set(working["_analysis_id"].astype(str)) if "_analysis_id" in working.columns else set()
    thermo = _flatten_thermodynamics(project_id, analysis_ids)
    minerals = sorted(working["Минерал"].dropna().astype(str).unique()) if "Минерал" in working.columns else []
    sources = sorted(working[SOURCE_LABEL_COLUMN].dropna().astype(str).unique()) if SOURCE_LABEL_COLUMN in working.columns else []

    badges = [
        (f"{len(working):,} анализов".replace(",", " "), "accent"),
        (f"{len(dataset_ids)} наборов", "neutral"),
        (f"{len(visible_images)} изображений", "neutral"),
        (f"{len(visible_entities)} объектов", "neutral"),
        (f"{len(thermo)} термодинамических результатов", "success" if len(thermo) else "neutral"),
    ]
    if local_query:
        badges.insert(1, (f"найдено из {len(dataframe):,}".replace(",", " "), "neutral"))
    render_badges(badges)

    section = st.segmented_control(
        "Раздел рабочего стола",
        ["Обзор", "Анализы", "Изображения", "Шлифы и объекты", "Термодинамика"],
        default="Анализы",
        key=f"workspace_section_{context_kind}",
    ) or "Анализы"

    if section == "Обзор":
        render_section_header(title, "Единый контекст объекта")
        if context_rows:
            st.dataframe(pd.DataFrame(context_rows, columns=["Поле", "Значение"]), width="stretch", hide_index=True)
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### Минералы")
            st.write(" · ".join(minerals)) if minerals else st.caption("Минеральных анализов в текущем отборе нет.")
        with c2:
            st.markdown("#### Источники")
            if sources:
                for source in sources[:20]:
                    st.caption(source)
            else:
                st.caption("Явные библиографические источники в текущем отборе не найдены.")

    elif section == "Анализы":
        render_analysis_table(
            working,
            project_id=project_id,
            key_prefix=f"workspace_{context_kind}_analyses",
            height=600,
        )
        _secondary_selection_actions(working, dataset_ids)

    elif section == "Изображения":
        render_asset_gallery(visible_images, max_items=40)

    elif section == "Шлифы и объекты":
        if not visible_entities:
            st.info("Связанных шлифов, зерен, точек или других физических объектов в текущем отборе нет.")
        else:
            view = pd.DataFrame(visible_entities)
            preferred = [column for column in ("kind", "name", "sample_name", "parent_name", "description", "created_at") if column in view.columns]
            st.dataframe(view[preferred], width="stretch", hide_index=True, height=520)
        if sample_id is not None and st.button("Открыть разметку шлифа", width="stretch", key=f"workspace_open_thin_{sample_id}"):
            navigate("thin_section")
            st.rerun()

    else:
        if thermo.empty:
            st.info("Сохранённых термодинамических расчётов для текущего контекста пока нет.")
            if st.button("Открыть термодинамику", type="primary", key="workspace_empty_thermo"):
                current_ids = list(read_selection().analysis_ids) or list(analysis_ids)
                st.session_state["thermodynamics_workspace_analysis_ids"] = current_ids
                st.session_state["thermodynamics_workspace_dataset_ids"] = dataset_ids
                navigate("thermobarometry")
                st.rerun()
        else:
            view = thermo.copy()
            if "_analysis_id" in view.columns:
                labels = {
                    str(row.get("_analysis_id")): human_point_label(row)
                    for _, row in dataframe.iterrows()
                }
                view.insert(0, "Точка", [labels.get(str(value), "") for value in view["_analysis_id"]])
            preferred = [column for column in (
                "Точка", "Метод", "Тип", "Thermodynamic status", "Thermobarometry status",
                "T (°C)", "P (kbar)", "ΔFMQ", "Актуальность", "Рассчитано", "Run",
            ) if column in view.columns]
            other = [column for column in view.columns if column not in preferred and not str(column).startswith("_")]
            st.dataframe(view[preferred + other], width="stretch", hide_index=True, height=600)


def _sample_workspace(project_id: int, query: str, datasets: list[dict]) -> None:
    samples = list_samples(project_id)
    matches = [sample for sample in samples if _query_match([
        sample.get("name", ""), sample.get("locality", ""), sample.get("field_lithology", ""), *sample.get("aliases", []),
    ], query)]
    if not matches:
        st.info("По этому запросу Sample не найден. Переключитесь на «Массив данных» или измените запрос.")
        return
    by_id = {int(sample["id"]): sample for sample in matches}
    ids = list(by_id)
    selected_id = st.selectbox(
        "Sample",
        ids,
        format_func=lambda value: f"{by_id[int(value)]['name']} · {by_id[int(value)].get('locality') or 'местность не указана'}",
        key="workspace_sample",
    )
    sample_row = by_id[int(selected_id)]
    sample_name = str(sample_row["name"])

    accessible_ids = [int(item["id"]) for item in datasets]
    frame = attach_study_metadata(load_unified_with_derived(project_id, accessible_ids)) if accessible_ids else pd.DataFrame()
    if "Sample" in frame.columns:
        frame = frame[frame["Sample"].astype(str).str.casefold() == sample_name.casefold()].copy()
    else:
        frame = frame.iloc[0:0].copy()
    dataset_ids = sorted({int(value) for value in frame.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()})
    analysis_ids = set(frame["_analysis_id"].astype(str)) if "_analysis_id" in frame.columns else set()
    all_images = list_image_records(project_id=project_id)
    images = [item for item in all_images if (
        set(str(value) for value in item.get("analysis_ids", [])) & analysis_ids
        or int(item.get("dataset_id") or -1) in dataset_ids
        or str(item.get("scope_value") or "").casefold() == sample_name.casefold()
    )]
    entities = list_entities(project_id, sample_id=int(sample_row["id"]))
    context_rows = [
        ("Sample", sample_name),
        ("Aliases", ", ".join(sample_row.get("aliases", [])) or "—"),
        ("Полевое название", str(sample_row.get("field_lithology") or "—")),
        ("Местность", str(sample_row.get("locality") or "—")),
        ("Описание", str(sample_row.get("description") or "—")),
        ("Заметки", str(sample_row.get("notes") or "—")),
    ]
    _workspace_tabs(
        project_id=project_id, title=f"Sample {sample_name}", dataframe=frame, dataset_ids=dataset_ids,
        images=images, entities=entities, context_rows=context_rows, context_kind="sample",
        context_label=sample_name, sample=sample_name, sample_id=int(sample_row["id"]),
    )


def _dataset_workspace(project_id: int, query: str, datasets: list[dict]) -> None:
    matches = [dataset for dataset in datasets if _query_match([
        dataset.get("name", ""), dataset.get("mineral_key", ""), dataset.get("source_filename", ""),
        dataset.get("source_sheet", ""), dataset.get("project_name", ""),
    ], query)]
    if not matches:
        st.info("По этому запросу массив данных не найден.")
        return
    by_id = {int(item["id"]): item for item in matches}
    ids = list(by_id)
    selected_id = st.selectbox(
        "Массив данных",
        ids,
        format_func=lambda value: f"{by_id[int(value)]['name']} · {by_id[int(value)].get('mineral_key') or 'mineral ?'} · {int(by_id[int(value)].get('row_count') or 0)} строк",
        key="workspace_dataset",
    )
    dataset = by_id[int(selected_id)]
    dataset_id = int(dataset["id"])
    frame = attach_study_metadata(load_unified_with_derived(project_id, [dataset_id]))
    sample_names = sorted(frame["Sample"].dropna().astype(str).unique()) if "Sample" in frame.columns else []
    entities: list[dict] = []
    sample_id = None
    sample_name = sample_names[0] if len(sample_names) == 1 else None
    if sample_name:
        sample_row = next((item for item in list_samples(project_id) if str(item["name"]).casefold() == sample_name.casefold()), None)
        if sample_row:
            sample_id = int(sample_row["id"])
            entities = list_entities(project_id, sample_id=sample_id)
    images = list_image_records(project_id=project_id, dataset_id=dataset_id)
    dataset_name = str(dataset.get("name") or "Массив")
    context_rows = [
        ("Массив", dataset_name),
        ("Минерал / режим", str(dataset.get("mineral_key") or "—")),
        ("Источник", str(dataset.get("source_filename") or "—")),
        ("Лист", str(dataset.get("source_sheet") or "—")),
        ("Тип источника", str(dataset.get("source_kind") or "—")),
        ("Sample в массиве", ", ".join(sample_names[:20]) if sample_names else "—"),
    ]
    _workspace_tabs(
        project_id=project_id, title=f"Массив {dataset_name}", dataframe=frame, dataset_ids=[dataset_id],
        images=images, entities=entities, context_rows=context_rows, context_kind="dataset",
        context_label=dataset_name, sample=sample_name, sample_id=sample_id,
    )


def render_object_workspace_page() -> None:
    project = active_project()
    render_page_header(
        "Рабочий стол",
        "Один Sample или один массив как единый научный объект. Отбор анализов сохраняется между таблицей, графиками и статистикой.",
        eyebrow="Основное",
        context=str(project["name"]) if project else "Проект не выбран",
    )
    if project is None:
        st.info("Сначала создайте или выберите проект.")
        return
    project_id = int(project["id"])
    datasets = list_accessible_datasets(project_id)
    mode = st.segmented_control(
        "Работать с", ["Sample", "Массив данных"],
        default=str(st.session_state.get("workspace_mode") or "Sample"), key="workspace_mode",
    ) or "Sample"
    incoming = str(st.session_state.pop("workspace_query_pending", "") or "")
    if incoming:
        st.session_state["workspace_query"] = incoming
    query = st.text_input(
        "Выбрать объект",
        key="workspace_query",
        placeholder="Начните вводить Sample или название массива…",
        help="Это поле выбирает сам объект. Внутри рабочего стола отдельный поиск фильтрует анализы и связанные материалы.",
    )
    if mode == "Sample":
        _sample_workspace(project_id, query, datasets)
    else:
        _dataset_workspace(project_id, query, datasets)

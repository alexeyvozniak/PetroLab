from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.measurement_registry import list_entities
from petrolab.repositories.image_repository import list_image_records
from petrolab.sample_registry import list_samples
from petrolab.source_registry import SOURCE_LABEL_COLUMN, attach_study_metadata
from petrolab.thermodynamics import list_thermodynamic_runs
from petrolab.thermobarometry import list_runs as list_legacy_thermobarometry_runs
from petrolab.ui.components import render_asset_gallery
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project
from petrolab.ui.work_context import set_work_context


_ID_COLUMNS = (
    "Sample", "Grain", "Point", "Generation", "Минерал", "Mineral", "Набор",
    SOURCE_LABEL_COLUMN, "QC уровень", "QC решение", "Method", "Метод", "_analysis_id",
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


def _route_selection(dataframe: pd.DataFrame, dataset_ids: list[int], scope_label: str) -> None:
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    analysis_ids = dataframe["_analysis_id"].astype(str).tolist()
    context = {
        "dataset_ids": [int(value) for value in dataset_ids],
        "analysis_ids": analysis_ids,
        "scope": scope_label,
    }
    render_section_header("Действия", "Текущий отбор передаётся дальше без копирования данных")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("График", type="primary", width="stretch", key="workspace_to_plot"):
        st.session_state["workflow_plot_dataset_ids"] = [int(value) for value in dataset_ids]
        st.session_state["workflow_plot_analysis_ids"] = analysis_ids
        st.session_state["workflow_plot_context"] = context
        st.session_state["workflow_plot_notice"] = f"В график передан отбор из {scope_label}."
        navigate("plots")
        st.rerun()
    if c2.button("Редактировать", width="stretch", key="workspace_to_edit"):
        st.session_state["workflow_edit_dataset_ids"] = [int(value) for value in dataset_ids]
        st.session_state["workflow_edit_analysis_ids"] = analysis_ids
        st.session_state["workflow_edit_context"] = context
        navigate("analyses")
        st.rerun()
    if c3.button("Таблица статьи", width="stretch", key="workspace_to_table"):
        st.session_state["workflow_table_dataset_ids"] = [int(value) for value in dataset_ids]
        st.session_state["workflow_table_analysis_ids"] = analysis_ids
        st.session_state["workflow_table_context"] = context
        navigate("article_tables")
        st.rerun()
    if c4.button("Термодинамика", width="stretch", key="workspace_to_thermo"):
        st.session_state["thermodynamics_workspace_analysis_ids"] = analysis_ids
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
            key=f"workspace_local_search_{context_kind}_{context_label}",
            placeholder=f"🔎 Найти в {context_label}…",
            label_visibility="collapsed",
        )
    with everywhere_col:
        if st.button("Везде", key=f"workspace_search_all_{context_kind}_{context_label}", width="stretch", help="Искать тот же запрос по всему проекту"):
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
    _route_selection(working, dataset_ids, f"{context_label}{' · поиск' if local_query else ''}")

    overview_tab, analyses_tab, images_tab, objects_tab, thermo_tab = st.tabs([
        "Обзор", "Анализы", "Изображения", "Шлифы и объекты", "Термодинамика",
    ])
    with overview_tab:
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

    with analyses_tab:
        if working.empty:
            st.info("Внутри текущего объекта по этому запросу анализов не найдено.")
        else:
            columns = _analysis_columns(working)
            st.dataframe(working[columns].head(2000), width="stretch", hide_index=True, height=600)
            if len(working) > 2000:
                st.caption(f"Показаны первые 2000 из {len(working)} строк.")

    with images_tab:
        render_asset_gallery(visible_images, max_items=40)

    with objects_tab:
        if not visible_entities:
            st.info("Связанных шлифов, зерен, точек или других физических объектов в текущем отборе нет.")
        else:
            view = pd.DataFrame(visible_entities)
            preferred = [column for column in ("kind", "name", "sample_name", "parent_name", "description", "created_at") if column in view.columns]
            st.dataframe(view[preferred], width="stretch", hide_index=True, height=520)
        if sample_id is not None and st.button("Открыть разметку шлифа", width="stretch", key=f"workspace_open_thin_{sample_id}"):
            navigate("thin_section")
            st.rerun()

    with thermo_tab:
        if thermo.empty:
            st.info("Сохранённых термодинамических расчётов для текущего отбора пока нет.")
            if st.button("Открыть термодинамику", type="primary", key="workspace_empty_thermo"):
                st.session_state["thermodynamics_workspace_analysis_ids"] = list(analysis_ids)
                st.session_state["thermodynamics_workspace_dataset_ids"] = dataset_ids
                navigate("thermobarometry")
                st.rerun()
        else:
            preferred = [column for column in (
                "_analysis_id", "Метод", "Тип", "Thermodynamic status", "Thermobarometry status",
                "T (°C)", "P (kbar)", "ΔFMQ", "Актуальность", "Рассчитано", "Run",
            ) if column in thermo.columns]
            other = [column for column in thermo.columns if column not in preferred]
            st.dataframe(thermo[preferred + other], width="stretch", hide_index=True, height=600)


def _sample_workspace(project_id: int, query: str, datasets: list[dict]) -> None:
    samples = list_samples(project_id)
    matches = [sample for sample in samples if _query_match([
        sample.get("name", ""), sample.get("locality", ""), sample.get("field_lithology", ""), *sample.get("aliases", []),
    ], query)]
    if not matches:
        st.info("По этому запросу Sample не найден. Переключитесь на «Массив данных» или измените запрос.")
        return
    labels = {f"{sample['name']} · {sample.get('locality') or 'местность не указана'} · id {int(sample['id'])}": sample for sample in matches}
    selected_label = st.selectbox("Sample", list(labels), key="workspace_sample")
    sample_row = labels[selected_label]
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
    labels = {f"{item['name']} · {item.get('mineral_key') or 'mineral ?'} · {int(item.get('row_count') or 0)} строк · id {int(item['id'])}": item for item in matches}
    selected_label = st.selectbox("Массив данных", list(labels), key="workspace_dataset")
    dataset = labels[selected_label]
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
    dataset_name = str(dataset.get("name") or dataset_id)
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
        "Один Sample или один массив как единый научный объект. После выбора лупа ищет только внутри него; кнопка «Везде» снимает ограничение.",
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
        help="Это поле выбирает сам объект. После выбора внутри рабочего стола появится отдельная лупа «Найти здесь».",
    )
    if mode == "Sample":
        _sample_workspace(project_id, query, datasets)
    else:
        _dataset_workspace(project_id, query, datasets)

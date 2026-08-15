from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.partition_import import import_partition_table, read_partition_upload
from petrolab.partition_seed_germ import GERM_CORE_NOTE, seed_germ_core_models
from petrolab.partition_seed_models import seed_initial_alkaline_models
from petrolab.partition_visuals import kd_table, onuma_figure, ree_d_figure, spider_figure
from petrolab.partitioning import assess_model_context, list_partition_models
from petrolab.ui.layout import render_hint, render_page_header
from petrolab.ui.project_context import active_project_id


_META = {"_analysis_id", "_dataset_id", "_project_id", "_row_index", "_source_row"}


def _distribution_dataset_map(datasets: list[dict]) -> dict[str, dict]:
    """Use immutable dataset IDs in UI labels so equal names cannot collapse."""
    return {dataset_label(dataset): dataset for dataset in datasets}


def render_distribution_page() -> None:
    render_page_header(
        "Распределение элементов",
        "Первый безопасный режим: наблюдаемые отношения двух конкретных анализов. Это не литературный равновесный D и не Kd обмена.",
        eyebrow="Исследование",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала выберите проект.")
        return

    with st.expander("Библиотека D: щелочные системы", expanded=False):
        st.caption(
            "Добавляет две экспериментальные модели LaTourrette et al. (1995): Phl–basanite melt и Amp–basanite melt. "
            "Они не заменяют ваши собственные D и не применяются автоматически."
        )
        if st.button("Добавить проверенные basanite-модели", key="partition_seed_basanite"):
            made = seed_initial_alkaline_models()
            st.success("Добавлено моделей: " + str(len(made)) if made else "Эти модели уже есть в библиотеке.")
        st.caption(GERM_CORE_NOTE)
        if st.button("Добавить встроенную библиотеку GERM: основные типы пород", key="partition_seed_germ"):
            made = seed_germ_core_models()
            st.success("Добавлено моделей GERM: " + str(len(made)) if made else "Эти выборки GERM уже есть в библиотеке.")

    with st.expander("Смотреть литературные коэффициенты D", expanded=False):
        models = list_partition_models()
        if not models:
            st.caption("Библиотека пока пуста: добавьте проверенные модели или импортируйте таблицу GERM.")
        else:
            rocks = sorted({
                str(model["applicability"].get("rock", "")).strip()
                for model in models
                if str(model["applicability"].get("rock", "")).strip()
            })
            rock_context = st.selectbox(
                "Контекст вашей породы (не ограничивает каталог)",
                ["Не задавать"] + rocks,
                help=(
                    "Например, при работе с лампрофиром фонолитные модели остаются видимыми: "
                    "появится только понятное предупреждение, но модель останется доступной."
                ),
                key="partition_rock_context",
            )
            query = st.text_input(
                "Поиск по породе, минералу, источнику или элементу",
                key="partition_catalogue_query",
            )
            context_value = None if rock_context == "Не задавать" else rock_context
            rows = []
            for model in models:
                source = model["source"]
                applicability = model["applicability"]
                context = assess_model_context(model, context_value)
                searchable = " ".join([
                    model["name"], model["mineral"], str(applicability.get("rock", "")),
                    str(source.get("citation", "")), " ".join(model["values"].keys()),
                ]).casefold()
                if query and query.casefold() not in searchable:
                    continue
                rows.append({
                    "ID": model["id"],
                    "Порода модели": applicability.get("rock", "—"),
                    "Минерал": model["mineral"],
                    "Фаза": model["counter_phase"],
                    "Определение D": source.get("kd_definition", "—"),
                    "Тип данных": source.get("kd_types", "—"),
                    "Статус относительно контекста": context["status"],
                    "Источник": source.get("citation", "—"),
                    "Элементов": len(model["values"]),
                })
            catalogue = pd.DataFrame(rows)
            st.caption(
                "Каталог ничего не отбрасывает. Предупреждение говорит лишь о границах опубликованной модели; "
                "оно не запрещает просмотр, экспорт или расчёт."
            )
            st.dataframe(catalogue, width="stretch", hide_index=True)
            if not catalogue.empty:
                chosen_id = st.selectbox(
                    "Открыть модель",
                    catalogue["ID"].tolist(),
                    format_func=lambda item: next(model["name"] for model in models if model["id"] == item),
                    key="partition_model_open",
                )
                chosen = next(model for model in models if model["id"] == chosen_id)
                metadata = chosen["source"].get("element_metadata", {})
                element_table = kd_table(chosen["values"], metadata)
                st.dataframe(
                    element_table.rename(columns={
                        "Element": "Элемент", "Kd": "Kd", "low": "Kd low", "high": "Kd high",
                    }),
                    width="stretch",
                    hide_index=True,
                )
                graph_tab, ree_tab, onuma_tab, spider_tab = st.tabs(["Обзор", "REE-D", "Onuma", "Kd-spider"])
                with graph_tab:
                    st.caption("Все графики показывают опубликованные коэффициенты выбранной модели; интервал и σ не усредняются.")
                    st.plotly_chart(spider_figure(element_table, chosen["name"]), width="stretch")
                with ree_tab:
                    st.plotly_chart(ree_d_figure(element_table, chosen["name"]), width="stretch")
                    st.caption("REE-D: логарифмическая шкала; σ показана, когда она опубликована.")
                with onuma_tab:
                    st.plotly_chart(onuma_figure(element_table, chosen["name"]), width="stretch")
                    st.caption("Onuma использует радиусы Shannon для CN VIII; это визуализация тренда, а не подгонка lattice-strain модели.")
                with spider_tab:
                    st.plotly_chart(spider_figure(element_table, chosen["name"]), width="stretch")
                chosen_context = assess_model_context(chosen, context_value)
                if chosen_context["status"] == "предупреждение":
                    st.warning(chosen_context["message"] + " Расчёт и просмотр доступны; это допущение будет записано в истории расчёта.")
                elif chosen_context["status"] == "соответствует":
                    st.success(chosen_context["message"])
                else:
                    st.info(chosen_context["message"])

    with st.expander("Импорт полной литературной таблицы D", expanded=False):
        upload = st.file_uploader(
            "GERM / собственная таблица (CSV, TSV или Excel)",
            type=["csv", "tsv", "txt", "xlsx", "xls"],
            key="partition_table_upload",
        )
        st.caption(
            "Поддерживается текущий экспорт GERM KdD: Rock Types, Minerals, Kd, Kd Sigma, Kd Low, Kd High, Definition и Type. "
            "Импортируются любые элементы, включая главные; интервал не превращается в среднее. Значения в GERM заданы по элементам, не по оксидам."
        )
        if upload is not None and st.button("Импортировать таблицу D", key="partition_table_import"):
            try:
                dataframe = read_partition_upload(upload.getvalue(), upload.name)
                made = import_partition_table(dataframe)
                st.success(f"Создано литературных моделей: {len(made)}")
            except Exception as exc:
                st.error(str(exc))

    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("В проекте пока нет анализов.")
        return
    labels = _distribution_dataset_map(datasets)
    options = list(labels)
    left_label = st.selectbox("Числитель: набор", options, key="ratio_left")
    right_label = st.selectbox("Знаменатель: набор", options, index=options.index(left_label), key="ratio_right")
    left = load_dataset_dataframe(int(labels[left_label]["id"]))
    right = load_dataset_dataframe(int(labels[right_label]["id"]))
    if left.empty or right.empty:
        st.info("В выбранном наборе нет анализов.")
        return

    left_ids = left["_analysis_id"].astype(str).tolist()
    right_ids = right["_analysis_id"].astype(str).tolist()
    a = st.selectbox("Точка в числителе", left_ids, key="ratio_left_analysis")
    b = st.selectbox("Точка в знаменателе", right_ids, key="ratio_right_analysis")
    row_a = left.loc[left["_analysis_id"].astype(str) == a].iloc[0]
    row_b = right.loc[right["_analysis_id"].astype(str) == b].iloc[0]

    candidates = [
        column for column in left.columns
        if column in right.columns
        and column not in _META
        and pd.api.types.is_numeric_dtype(left[column])
        and pd.api.types.is_numeric_dtype(right[column])
    ]
    records = []
    for column in candidates:
        x = pd.to_numeric(row_a[column], errors="coerce")
        y = pd.to_numeric(row_b[column], errors="coerce")
        status = (
            "measured" if pd.notna(x) and pd.notna(y) and y != 0
            else "zero denominator" if pd.notna(y) and y == 0
            else "missing"
        )
        records.append({
            "Component": column,
            "Numerator": x,
            "Denominator": y,
            "Observed ratio": x / y if status == "measured" else np.nan,
            "Status": status,
        })
    table = pd.DataFrame(records)
    render_hint(
        "Интерпретируйте это как C₁/C₂. Для equilibrium D нужны Assemblage, CompositionSet и выбранная литературная модель — они будут отдельным следующим режимом."
    )
    st.dataframe(table, width="stretch", hide_index=True)
    plotted = table.loc[table["Status"] == "measured"].copy()
    if not plotted.empty:
        figure = go.Figure(go.Scatter(
            x=plotted["Component"],
            y=np.log10(plotted["Observed ratio"]),
            mode="lines+markers",
            name="log10(C₁/C₂)",
        ))
        figure.update_layout(
            yaxis_title="log10 observed ratio",
            xaxis_title="",
            height=380,
            margin=dict(l=30, r=20, t=20, b=60),
        )
        st.plotly_chart(figure, width="stretch")
    st.download_button(
        "Скачать observed ratios (CSV)",
        table.to_csv(index=False).encode("utf-8-sig"),
        "observed_ratios.csv",
        "text/csv",
        key="ratio_download",
    )

from __future__ import annotations

import io

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_accessible_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.thermodynamics import (
    FERRY_WATSON_2007_TI_ZIRCON,
    KIND_FUGACITY,
    KIND_PRESSURE,
    KIND_TEMPERATURE,
    LOUCKS_2020_ZIRCON_DFMQ,
    METHODS,
    MODE_MINERAL_MELT,
    MODE_SINGLE_MINERAL,
    MUTCH_2016_AMP_BAROMETER,
    PUTIRKA_2008_CPX_ONLY,
    PUTIRKA_2008_OL_LIQ_EQ22,
    PUTIRKA_2016_AMP_EQ5,
    calculate_method,
    list_thermodynamic_runs,
    method_by_id,
    save_thermodynamic_run,
)
from petrolab.thermobarometry import (
    QC_FAIL,
    QC_INSUFFICIENT_INPUT,
    QC_PASS,
    QC_WARNING,
    list_runs as list_legacy_runs,
)
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.project_context import active_project_id


_IDENTITY_COLUMNS = ("Sample", "Grain", "Point", "Generation", "Набор", "Минерал", "_analysis_id")
_KIND_LABELS = {
    KIND_TEMPERATURE: "Термометры",
    KIND_PRESSURE: "Барометры",
    KIND_FUGACITY: "Фугометры / oxybarometers",
}
_MODE_LABELS = {
    MODE_SINGLE_MINERAL: "Мономинеральные",
    MODE_MINERAL_MELT: "Минерал–расплав",
}
_CONTEXT_TOKEN_KEY = "_thermodynamics_context_token"


def _identity_columns(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in _IDENTITY_COLUMNS if column in dataframe.columns]


def _method_label(method_id: str) -> str:
    method = method_by_id(method_id)
    return f"{method.short_title} · {_MODE_LABELS[method.input_mode]}"


def _candidate_method_ids(datasets: list[dict]) -> list[str]:
    minerals = {str(item.get("mineral_key") or "") for item in datasets}
    return [method.method_id for method in METHODS if method.mineral_key in minerals]


def _incoming_context() -> tuple[list[int], set[str]]:
    dataset_ids = [
        int(value) for value in st.session_state.get("thermodynamics_workspace_dataset_ids", [])
        if value is not None
    ]
    analysis_ids = {
        str(value) for value in st.session_state.get("thermodynamics_workspace_analysis_ids", [])
        if str(value)
    }
    return list(dict.fromkeys(dataset_ids)), analysis_ids


def _clear_incoming_context() -> None:
    st.session_state.pop("thermodynamics_workspace_dataset_ids", None)
    st.session_state.pop("thermodynamics_workspace_analysis_ids", None)
    st.session_state.pop(_CONTEXT_TOKEN_KEY, None)
    st.session_state.pop("thermodynamics_limit_incoming", None)
    st.session_state.pop("thermodynamics_datasets", None)
    st.session_state.pop("thermodynamics_selection_mode", None)


def _filtered_source(project_id: int, dataset_ids: list[int], mineral_key: str, query: str) -> pd.DataFrame:
    source = load_unified_with_derived(project_id, dataset_ids)
    if "Минерал" in source.columns:
        source = source[source["Минерал"].astype(str) == mineral_key].copy()
    if "_analysis_id" in source.columns:
        source = source.drop_duplicates("_analysis_id")
    if query.strip() and not source.empty:
        needle = query.strip().casefold()
        mask = pd.Series(False, index=source.index)
        for column in _identity_columns(source):
            mask |= source[column].astype(str).str.casefold().str.contains(needle, na=False)
        source = source.loc[mask].copy()
    return source.reset_index(drop=True)


def _point_selection(source: pd.DataFrame) -> pd.DataFrame:
    choice = st.radio(
        "Точки",
        ["Все отфильтрованные", "Выбрать вручную"],
        horizontal=True,
        key="thermodynamics_selection_mode",
    )
    preview = _identity_columns(source)
    extra = [
        column for column in (
            "SiO2", "TiO2", "Al2O3", "FeOt", "FeO", "MgO", "CaO", "Na2O", "K2O",
            "Ti [µg/g]", "Ce [µg/g]", "Ui [µg/g]", "U [µg/g]",
        ) if column in source.columns and column not in preview
    ]
    columns = preview + extra
    if choice == "Все отфильтрованные":
        st.dataframe(source[columns].head(500), width="stretch", hide_index=True, height=285)
        if len(source) > 500:
            st.caption(f"Показаны первые 500 из {len(source)} точек; расчёт охватит весь текущий отбор.")
        return source.copy()

    editor = source[columns].copy()
    editor.insert(0, "Рассчитать", False)
    edited = st.data_editor(
        editor,
        width="stretch",
        hide_index=True,
        height=330,
        key="thermodynamics_point_selector",
        column_config={"Рассчитать": st.column_config.CheckboxColumn("Рассчитать")},
        disabled=[column for column in editor.columns if column != "Рассчитать"],
    )
    ids = edited.loc[edited["Рассчитать"], "_analysis_id"].astype(str).tolist()
    return source[source["_analysis_id"].astype(str).isin(ids)].copy()


def _melt_editor() -> dict[str, float]:
    st.markdown("#### Представительный состав расплава")
    st.caption(
        "Один явно заданный состав расплава применяется ко всем выбранным olivine. "
        "Автоматический перебор mineral–melt пар намеренно не выполняется."
    )
    fields = ("SiO2", "TiO2", "Al2O3", "FeOt", "MnO", "MgO", "CaO", "Na2O", "K2O", "H2O")
    values: dict[str, float] = {}
    for start in range(0, len(fields), 5):
        cols = st.columns(min(5, len(fields) - start))
        for widget, field in zip(cols, fields[start:start + 5]):
            values[field] = float(widget.number_input(
                field + " (wt%)",
                min_value=0.0,
                value=0.0,
                step=0.1,
                key=f"thermodynamics_melt_{field}",
            ))
    return values


def _method_assumptions(method_id: str) -> tuple[dict, dict | None]:
    assumptions: dict = {}
    melt: dict | None = None
    if method_id == PUTIRKA_2008_CPX_ONLY.method_id:
        assumptions["pressure_kbar"] = float(st.number_input(
            "Независимо заданное давление (kbar)", min_value=0.0, value=2.0, step=0.1,
            key="thermodynamics_cpx_pressure",
        ))
        assumptions["applicability_confirmed"] = st.checkbox(
            "Подтверждаю применимость anhydrous Cpx-only Eq. 32d к этому отбору.",
            key="thermodynamics_cpx_confirm",
        )
    elif method_id == PUTIRKA_2016_AMP_EQ5.method_id:
        assumptions["applicability_confirmed"] = st.checkbox(
            "Подтверждаю, что это магматические calcic amphiboles и текстурный контекст позволяет применять Eq. 5.",
            key="thermodynamics_amp_t_confirm",
        )
    elif method_id == MUTCH_2016_AMP_BAROMETER.method_id:
        assumptions["assemblage_confirmed"] = st.checkbox(
            "Подтверждаю критерии Mutch et al.: гранитная низковариантная ассоциация, rim-анализы amphibole, контакт/равновесие с plagioclase и near-solidus условия.",
            key="thermodynamics_mutch_confirm",
        )
        if not assumptions["assemblage_confirmed"]:
            st.warning(
                "Без подтверждения строгой области применимости PetroLab покажет диагностическое P, "
                "но сохранит результат как WARNING, а не PASS."
            )
    elif method_id == FERRY_WATSON_2007_TI_ZIRCON.method_id:
        c1, c2 = st.columns(2)
        assumptions["a_sio2"] = float(c1.number_input(
            "aSiO₂", min_value=0.01, max_value=1.0, value=1.0, step=0.05,
            key="thermodynamics_zrn_asio2",
        ))
        assumptions["a_tio2"] = float(c2.number_input(
            "aTiO₂", min_value=0.01, max_value=1.0, value=1.0, step=0.05,
            key="thermodynamics_zrn_atio2",
        ))
        st.caption("1.0 означает буфер соответствующей чистой фазы; снижайте активность только при петрологическом основании.")
    elif method_id == LOUCKS_2020_ZIRCON_DFMQ.method_id:
        assumptions["allow_measured_u_as_initial"] = st.checkbox(
            "Разрешить использовать измеренный U вместо age-corrected Ui, если отдельной колонки Ui нет",
            key="thermodynamics_zrn_u_confirm",
            help="PetroLab не выполняет скрытую age correction. При этом выборе результат будет WARNING.",
        )
    elif method_id == PUTIRKA_2008_OL_LIQ_EQ22.method_id:
        assumptions["pressure_kbar"] = float(st.number_input(
            "Давление (kbar)", min_value=0.0, value=2.0, step=0.1,
            key="thermodynamics_ol_liq_pressure",
        ))
        assumptions["equilibrium_confirmed"] = st.checkbox(
            "Подтверждаю, что выбранные olivine и заданный расплав генетически связаны и их сопоставление петрологически оправдано.",
            key="thermodynamics_ol_liq_confirm",
        )
        melt = _melt_editor()
    return assumptions, melt


def _method_contract(method_id: str) -> None:
    method = method_by_id(method_id)
    with st.expander("Метод, ограничения и источник", expanded=False):
        st.write(f"**Калибровка:** {method.title}")
        st.write(f"**Источник:** {method.source_citation}")
        st.write(f"**DOI:** {method.source_doi}")
        st.write(f"**Версия уравнения:** {method.equation_version}")
        st.write(f"**Ошибка / precision:** {method.uncertainty}")
        st.write(f"**Область применимости:** {method.calibration_range}")
        if method.required_mineral_components:
            st.write("**Минеральные входы:** " + ", ".join(method.required_mineral_components))
        if method.required_melt_components:
            st.write("**Расплав:** " + ", ".join(method.required_melt_components))
        if method.assumptions:
            st.warning(method.assumptions)


def _result_badges(result: pd.DataFrame) -> None:
    counts = result["Thermodynamic status"].value_counts() if "Thermodynamic status" in result else pd.Series(dtype=int)
    render_badges([
        (f"{len(result)} результатов", "neutral"),
        (f"{int(counts.get(QC_PASS, 0))} PASS", "success"),
        (f"{int(counts.get(QC_WARNING, 0))} WARNING", "warning"),
        (f"{int(counts.get(QC_FAIL, 0))} FAIL", "danger"),
        (f"{int(counts.get(QC_INSUFFICIENT_INPUT, 0))} неполных", "warning"),
    ])


def _run_history(project_id: int) -> None:
    current = list_thermodynamic_runs(project_id)
    legacy = list_legacy_runs(project_id)
    if not current and not legacy:
        return
    with st.expander("История расчётов", expanded=False):
        rows = []
        for run in current[:100]:
            rows.append({
                "Run": run.id,
                "Метод": run.method_title,
                "Режим": _MODE_LABELS.get(run.input_mode, run.input_mode),
                "Тип": _KIND_LABELS.get(run.parameter_kind, run.parameter_kind),
                "Точек": len(run.input_analysis_ids),
                "Актуальность": "Актуален" if run.is_current else "Требует пересчёта",
                "Время": run.calculated_at,
            })
        for run in legacy[:50]:
            rows.append({
                "Run": f"legacy-{run.id}",
                "Метод": run.method_title,
                "Режим": "Мономинеральный · legacy",
                "Тип": "Термометр",
                "Точек": len(run.input_analysis_ids),
                "Актуальность": "Актуален" if run.is_current else "Требует пересчёта",
                "Время": run.calculated_at,
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=min(520, 70 + 34 * len(rows)))
        st.caption(
            "Расчёты привязаны к immutable _analysis_id и отпечаткам исходной химии. "
            "После изменения входной химии старый run сохраняется как история, но перестаёт считаться актуальным."
        )


def render_thermobarometry_page() -> None:
    render_page_header(
        "Термодинамика",
        "Мономинеральные и mineral–melt термометры, барометры и oxybarometers с provenance, QC и историей по каждой аналитической точке.",
        eyebrow="Исследование",
        context="Биминеральные методы пока намеренно отключены",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте или выберите проект.")
        return

    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.info("В активном проекте нет аналитических наборов.")
        _run_history(project_id)
        return

    requested_dataset_ids, requested_analysis_ids = _incoming_context()
    accessible_ids = {int(item["id"]) for item in datasets}
    requested_dataset_ids = [value for value in requested_dataset_ids if value in accessible_ids]
    context_datasets = [item for item in datasets if int(item["id"]) in requested_dataset_ids]
    method_scope = context_datasets or datasets
    method_ids = _candidate_method_ids(method_scope)
    if not method_ids:
        method_ids = _candidate_method_ids(datasets)
    if not method_ids:
        st.info("Для минералов активного проекта пока нет зарегистрированных термодинамических калибровок.")
        _run_history(project_id)
        return

    if requested_dataset_ids or requested_analysis_ids:
        with st.container(border=True):
            st.markdown("**Получен отбор из рабочего стола / карточки анализа**")
            st.caption(
                f"Наборов: {len(requested_dataset_ids) if requested_dataset_ids else 'не задано'} · "
                f"точек: {len(requested_analysis_ids) if requested_analysis_ids else 'весь объект'}. "
                "Можно сохранить этот точный отбор или отключить ограничение ниже."
            )
            c1, c2 = st.columns([3, 1])
            limit_incoming = c1.checkbox(
                "Ограничить расчёт исходным отбором точек",
                value=True,
                key="thermodynamics_limit_incoming",
                disabled=not requested_analysis_ids,
            )
            if c2.button("Сбросить отбор", width="stretch", key="thermodynamics_clear_context"):
                _clear_incoming_context()
                st.rerun()
    else:
        limit_incoming = False

    render_badges([
        ("Мономинеральные", "accent"),
        ("Минерал–расплав", "accent"),
        ("T · P · ΔFMQ", "neutral"),
        ("Без биминеральных пар", "neutral"),
        ("Исходная химия read-only", "success"),
    ])

    render_section_header("1. Метод", "Показываются только калибровки для минералов текущего контекста")
    kind_options = [
        kind for kind in (KIND_TEMPERATURE, KIND_PRESSURE, KIND_FUGACITY)
        if any(method_by_id(mid).parameter_kind == kind for mid in method_ids)
    ]
    preferred_kind = method_by_id(method_ids[0]).parameter_kind
    current_kind = st.session_state.get("thermodynamics_kind")
    if current_kind not in kind_options:
        st.session_state["thermodynamics_kind"] = preferred_kind
    kind = st.segmented_control(
        "Что считать",
        kind_options,
        default=preferred_kind,
        format_func=lambda value: _KIND_LABELS[value],
        key="thermodynamics_kind",
    ) or preferred_kind
    filtered_methods = [mid for mid in method_ids if method_by_id(mid).parameter_kind == kind]
    current_method = st.session_state.get("thermodynamics_method")
    if current_method not in filtered_methods:
        st.session_state["thermodynamics_method"] = filtered_methods[0]
    method_id = st.selectbox(
        "Калибровка",
        filtered_methods,
        format_func=_method_label,
        key="thermodynamics_method",
    )
    method = method_by_id(method_id)
    _method_contract(method_id)

    render_section_header("2. Данные", f"Минерал: {method.mineral_key} · режим: {_MODE_LABELS[method.input_mode]}")
    candidate_datasets = [item for item in datasets if str(item.get("mineral_key") or "") == method.mineral_key]
    labels = {dataset_label(item): int(item["id"]) for item in candidate_datasets}
    requested_labels = [label for label, dataset_id in labels.items() if dataset_id in requested_dataset_ids]
    context_token = (
        tuple(sorted(requested_dataset_ids)),
        tuple(sorted(requested_analysis_ids)),
        method.mineral_key,
    )
    if (requested_dataset_ids or requested_analysis_ids) and st.session_state.get(_CONTEXT_TOKEN_KEY) != context_token:
        st.session_state[_CONTEXT_TOKEN_KEY] = context_token
        if requested_labels:
            st.session_state["thermodynamics_datasets"] = requested_labels
        else:
            st.session_state.pop("thermodynamics_datasets", None)
        st.session_state["thermodynamics_selection_mode"] = "Все отфильтрованные"
    current_dataset_labels = st.session_state.get("thermodynamics_datasets")
    if isinstance(current_dataset_labels, list):
        valid_dataset_labels = [value for value in current_dataset_labels if value in labels]
        if valid_dataset_labels != current_dataset_labels:
            st.session_state["thermodynamics_datasets"] = valid_dataset_labels or (requested_labels or list(labels))
    selected_labels = st.multiselect(
        "Наборы",
        list(labels),
        default=requested_labels or list(labels),
        key="thermodynamics_datasets",
    )
    if not selected_labels:
        st.info("Выберите хотя бы один набор.")
        _run_history(project_id)
        return
    dataset_ids = [labels[label] for label in selected_labels]
    query = st.text_input(
        "Фильтр по Sample / Grain / Point / Generation",
        key="thermodynamics_search",
    )
    source = _filtered_source(project_id, dataset_ids, method.mineral_key, query)
    if requested_analysis_ids and limit_incoming and "_analysis_id" in source.columns:
        source = source[source["_analysis_id"].astype(str).isin(requested_analysis_ids)].copy()
        st.caption(f"Точный входной контекст: {len(source)} подходящих точек для выбранного метода.")
    if source.empty or "_analysis_id" not in source.columns:
        st.warning("В текущем отборе нет подходящих анализов со стабильным _analysis_id.")
        _run_history(project_id)
        return
    selection = _point_selection(source)
    if selection.empty:
        st.info("Отметьте хотя бы одну аналитическую точку.")
        _run_history(project_id)
        return

    render_section_header("3. Допущения", "PetroLab не угадывает давление, активности, равновесие или age correction")
    assumptions, melt = _method_assumptions(method_id)

    try:
        result = calculate_method(method_id, selection, assumptions=assumptions, melt=melt)
    except Exception as exc:
        st.error(f"Расчёт остановлен: {exc}")
        _run_history(project_id)
        return

    render_section_header("4. Предпросмотр и QC", "Число может быть показано диагностически даже при WARNING; статус хранится вместе с результатом")
    _result_badges(result)
    display = pd.concat([
        selection[_identity_columns(selection)].reset_index(drop=True),
        result.reset_index(drop=True),
    ], axis=1)
    st.dataframe(display.head(1000), width="stretch", hide_index=True, height=390)

    save_col, export_col = st.columns([1.2, 1])
    if save_col.button(
        "Сохранить расчёт",
        type="primary",
        width="stretch",
        key="save_thermodynamic_run",
    ):
        try:
            saved = save_thermodynamic_run(
                project_id,
                method_id=method_id,
                source_dataframe=selection,
                results_dataframe=result,
                assumptions=assumptions,
                melt=melt,
            )
        except Exception as exc:
            st.error(f"Расчёт не сохранён: {exc}")
        else:
            st.success(
                f"Сохранён run #{saved.id}. Теперь параметры доступны из карточки каждой точки через «＋ Термодинамические параметры»."
            )
            st.rerun()

    csv = display.to_csv(index=False).encode("utf-8-sig")
    export_col.download_button(
        "CSV текущего расчёта",
        data=io.BytesIO(csv),
        file_name=f"petrolab_{method_id}.csv",
        mime="text/csv",
        width="stretch",
    )
    _run_history(project_id)

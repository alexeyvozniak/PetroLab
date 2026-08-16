from __future__ import annotations

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label, human_point_label
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.derived import (
    formula_status,
    load_dataset_with_derived,
    save_formula_results,
    save_point_formula_results,
)
from petrolab.formula_workflow import recommended_method
from petrolab.mineral_assignments import attach_mineral_assignments
from petrolab.minerals.classification import CLASSIFICATION_COLUMNS
from petrolab.minerals.formulae import methods_for
from petrolab.repositories.rock_repository import composition_wide
from petrolab.services.formula_service import calculate_formula_safe
from petrolab.ui.layout import render_badges, render_page_header, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui.selection_context import read_selection
from petrolab.user_derived import (
    FORMULA_PRESETS,
    TARGET_DATASET,
    TARGET_ROCK_PROJECT,
    delete_field,
    evaluate_expression,
    list_dataset_fields,
    list_rock_project_fields,
    save_dataset_field,
    save_rock_project_field,
    set_field_enabled,
)


def _derived_columns(source: pd.DataFrame, result: pd.DataFrame) -> list[str]:
    return [str(column) for column in result.columns if column not in source.columns and not str(column).startswith("_")]


def _identity_columns(dataframe: pd.DataFrame) -> list[str]:
    return [column for column in ("Sample", "Grain", "Point", "Generation") if column in dataframe.columns]


def _render_classification_summary(result: pd.DataFrame) -> None:
    columns = [column for column in CLASSIFICATION_COLUMNS if column in result.columns]
    if not columns:
        return
    render_section_header("Автоматическая классификация", "Формальное имя только при достаточных данных")
    view = result[_identity_columns(result) + columns].copy()
    if "_analysis_id" in result.columns:
        view.insert(0, "Точка", [human_point_label(row) for _, row in result.iterrows()])
    st.dataframe(
        view.head(1000),
        width="stretch", hide_index=True,
        height=min(420, 42 + 35 * min(len(result), 10)),
    )


def _render_full_validity_summary(result: pd.DataFrame) -> None:
    if "formula_valid" not in result.columns:
        return
    valid = result["formula_valid"].fillna(False).astype(bool)
    invalid = ~valid
    render_badges([
        (f"{int(valid.sum()):,} валидных формул".replace(",", " "), "success"),
        (f"{int(invalid.sum()):,} не рассчитаны".replace(",", " "), "warning" if invalid.any() else "neutral"),
    ])
    if invalid.any():
        problem_columns = _identity_columns(result) + [
            column for column in [
                "formula_invalid_reason", "QC formula input", "Formula missing inputs",
                "QC суммы", "QC химии", "QC железа",
            ] if column in result.columns
        ]
        problem = result.loc[invalid].copy()
        view = problem[problem_columns].copy()
        if "_analysis_id" in problem.columns:
            view.insert(0, "Точка", [human_point_label(row) for _, row in problem.iterrows()])
        st.markdown("#### Проблемные строки")
        st.caption(
            "Невалидные строки сохраняют source chemistry, но formula-derived поля для них остаются пустыми."
        )
        st.dataframe(
            view.head(2000),
            width="stretch", hide_index=True, height=min(520, 45 + 28 * min(int(invalid.sum()), 16)),
        )
        if int(invalid.sum()) > 2000:
            st.caption(f"Показано 2000 из {int(invalid.sum())} проблемных строк.")


def _formula_token(column: str) -> str:
    text = str(column)
    if text.isidentifier() and not text.startswith("_"):
        return text
    return f"`{text}`"


def _append_formula_token(expression_key: str, column: str) -> None:
    if column == "—":
        return
    current = str(st.session_state.get(expression_key, "")).rstrip()
    token = _formula_token(column)
    st.session_state[expression_key] = f"{current} {token}".strip()


def _saved_fields(target_kind: str, target_id: int):
    if target_kind == TARGET_DATASET:
        return list_dataset_fields(target_id)
    return list_rock_project_fields(target_id)


def _save_user_field(
    target_kind: str,
    target_id: int,
    *,
    name: str,
    expression: str,
    unit: str,
    dependencies: tuple[str, ...],
    description: str,
):
    if target_kind == TARGET_DATASET:
        return save_dataset_field(
            target_id,
            name=name,
            expression=expression,
            unit=unit,
            dependencies=dependencies,
            description=description,
        )
    return save_rock_project_field(
        target_id,
        name=name,
        expression=expression,
        unit=unit,
        dependencies=dependencies,
        description=description,
    )


def _render_saved_user_fields(target_kind: str, target_id: int, key_prefix: str) -> None:
    fields = _saved_fields(target_kind, target_id)
    if not fields:
        st.caption("Сохранённых пользовательских формул пока нет.")
        return
    table = pd.DataFrame([
        {
            "Поле": field.name,
            "Формула": field.expression,
            "Единица": field.unit or "не определена",
            "Входы": ", ".join(field.dependencies),
            "Статус": "включено" if field.enabled else "отключено",
        }
        for field in fields
    ])
    st.dataframe(table, width="stretch", hide_index=True, height=min(330, 42 + 35 * min(len(table), 8)))
    field_map = {f"{field.name} · {field.expression}": field for field in fields}
    selected_label = st.selectbox(
        "Управление сохранённой формулой",
        list(field_map),
        key=f"{key_prefix}_manage_field",
    )
    selected = field_map[selected_label]
    c1, c2 = st.columns(2)
    toggle_label = "Отключить" if selected.enabled else "Включить"
    if c1.button(toggle_label, key=f"{key_prefix}_toggle_{selected.id}", width="stretch"):
        set_field_enabled(selected.id, not selected.enabled)
        st.rerun()
    if c2.button("Удалить", key=f"{key_prefix}_delete_{selected.id}", width="stretch"):
        delete_field(selected.id)
        st.rerun()


def _render_user_field_builder(
    dataframe: pd.DataFrame,
    *,
    target_kind: str,
    target_id: int,
    key_prefix: str,
    identity_columns: list[str],
) -> None:
    if dataframe.empty:
        st.info("Нет строк, на которых можно проверить формулу.")
        return

    existing_fields = _saved_fields(target_kind, target_id)
    existing_names = {field.name for field in existing_fields}
    visible_columns = [str(column) for column in dataframe.columns if not str(column).startswith("_")]
    expression_key = f"{key_prefix}_expression"

    with st.expander("Создать или изменить вычисляемое поле", expanded=not existing_fields):
        preset_map = {preset["label"]: preset for preset in FORMULA_PRESETS}
        preset_label = st.selectbox(
            "Готовая формула",
            ["Своя формула", *preset_map],
            key=f"{key_prefix}_preset",
        )
        if preset_label != "Своя формула" and st.button(
            "Подставить выбранную формулу",
            key=f"{key_prefix}_apply_preset",
            width="stretch",
        ):
            preset = preset_map[preset_label]
            st.session_state[f"{key_prefix}_name"] = preset["name"]
            st.session_state[expression_key] = preset["expression"]
            st.rerun()

        name = st.text_input("Название новой колонки", key=f"{key_prefix}_name")
        expression = st.text_area(
            "Формула",
            key=expression_key,
            height=90,
            help=(
                "Разрешены +, -, *, /, ** и скобки. Простые имена можно писать напрямую: La / Yb. "
                "Точное имя сложной колонки заключайте в обратные кавычки, например `La [µg/g]`."
            ),
        )

        c1, c2 = st.columns([3, 1])
        insert_column = c1.selectbox(
            "Добавить колонку в формулу",
            ["—", *visible_columns],
            key=f"{key_prefix}_insert_column",
        )
        c2.button(
            "Добавить",
            key=f"{key_prefix}_insert_button",
            width="stretch",
            disabled=insert_column == "—",
            on_click=_append_formula_token,
            args=(expression_key, insert_column),
        )

        description = st.text_input("Комментарий / смысл показателя", key=f"{key_prefix}_description")
        preview = None
        preview_error = ""
        clean_name = str(name).strip()
        if expression.strip():
            preview_frame = dataframe
            if clean_name in existing_names and clean_name in preview_frame.columns:
                preview_frame = preview_frame.drop(columns=[clean_name])
            try:
                preview = evaluate_expression(preview_frame, expression)
            except ValueError as exc:
                preview_error = str(exc)
                st.error(preview_error)

        if preview is not None:
            unit_label = "безразмерная" if preview.unit == "1" else (preview.unit or "не определена")
            render_badges([
                (f"Единица: {unit_label}", "accent" if preview.unit else "warning"),
                (f"Входов: {len(preview.dependencies)}", "neutral"),
                (f"Строк: {int(preview.values.notna().sum())}/{len(preview.values)}", "success"),
            ])
            st.caption("Используются: " + ", ".join(preview.dependencies))
            for warning in preview.warnings:
                st.warning(warning)
            preview_table = dataframe[identity_columns].copy() if identity_columns else pd.DataFrame(index=dataframe.index)
            preview_table[clean_name or "Результат"] = preview.values
            st.dataframe(preview_table.head(20), width="stretch", hide_index=True, height=260)

        name_conflict = bool(clean_name and clean_name in dataframe.columns and clean_name not in existing_names)
        if name_conflict:
            st.error("Такое имя уже занято исходной или системной колонкой. Выберите другое название.")
        can_save = bool(clean_name and preview is not None and not preview_error and not name_conflict)
        if st.button(
            "Сохранить вычисляемое поле",
            type="primary",
            disabled=not can_save,
            key=f"{key_prefix}_save",
            width="stretch",
        ):
            _save_user_field(
                target_kind,
                target_id,
                name=clean_name,
                expression=expression,
                unit=preview.unit,
                dependencies=preview.dependencies,
                description=description,
            )
            st.success(f"Поле «{clean_name}» сохранено и будет пересчитываться автоматически.")
            st.rerun()

    _render_saved_user_fields(target_kind, target_id, key_prefix)


def _requested_dataset_id(datasets: list[dict]) -> int | None:
    ids = {int(item["id"]) for item in datasets}
    legacy = st.session_state.pop("workflow_formula_dataset_id", None)
    pending = st.session_state.pop("formulae_dataset_ids_pending", [])
    candidates: list[int] = []
    if legacy is not None:
        try:
            candidates.append(int(legacy))
        except (TypeError, ValueError):
            pass
    for value in pending or []:
        try:
            candidates.append(int(value))
        except (TypeError, ValueError):
            continue
    return next((value for value in candidates if value in ids), None)


def _selection_ids_for_dataset(raw_source: pd.DataFrame) -> list[str]:
    pending = [str(value) for value in st.session_state.pop("formulae_analysis_ids_pending", []) if str(value)]
    canonical = list(read_selection().analysis_ids)
    wanted = list(dict.fromkeys([*pending, *canonical]))
    if not wanted or "_analysis_id" not in raw_source.columns:
        return []
    available = set(raw_source["_analysis_id"].astype(str))
    return [value for value in wanted if value in available]


def render_formulae_page() -> None:
    render_page_header(
        "Расчёты",
        "Пользовательские индексы, отношения и суммы, а также структурные формулы/APFU — без изменения исходной химии.",
        eyebrow="Данные",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return

    datasets = list_accessible_datasets(project_id)
    chosen = None
    raw_source = pd.DataFrame()
    dataset_id = None

    render_section_header(
        "Вычисляемые поля",
        "Суммы, отношения и произвольная арифметика. Сохранённые выражения пересчитываются при каждом чтении данных.",
    )
    if datasets:
        mapping = {dataset_label(dataset): dataset for dataset in datasets}
        dataset_labels = list(mapping)
        requested_dataset = _requested_dataset_id(datasets)
        if requested_dataset is not None:
            st.session_state.pop("formula_dataset", None)
            st.session_state.pop("formula_method", None)
        requested_label = next(
            (label for label, dataset in mapping.items() if int(dataset["id"]) == int(requested_dataset)),
            None,
        ) if requested_dataset is not None else None
        dataset_index = dataset_labels.index(requested_label) if requested_label in dataset_labels else 0
        chosen = mapping[st.selectbox("Набор анализов", dataset_labels, index=dataset_index, key="formula_dataset")]
        dataset_id = int(chosen["id"])
        raw_source = load_dataset_dataframe(dataset_id, include_meta=True)
        analysis_source = load_dataset_with_derived(dataset_id, include_meta=True)
        _render_user_field_builder(
            analysis_source,
            target_kind=TARGET_DATASET,
            target_id=dataset_id,
            key_prefix=f"analysis_formula_{dataset_id}",
            identity_columns=_identity_columns(analysis_source),
        )
        runtime_warnings = analysis_source.attrs.get("user_derived_warnings", [])
        if runtime_warnings:
            with st.expander(f"Предупреждения сохранённых формул: {len(runtime_warnings)}", expanded=False):
                for warning in runtime_warnings:
                    st.warning(str(warning))
    else:
        st.info("В активном проекте пока нет наборов анализов. Формулы для пород доступны ниже.")

    with st.expander("Вычисляемые поля для пород / whole-rock", expanded=not datasets):
        rock_source = composition_wide(project_id)
        if rock_source.empty:
            st.info("В проекте пока нет whole-rock составов.")
        else:
            _render_user_field_builder(
                rock_source,
                target_kind=TARGET_ROCK_PROJECT,
                target_id=project_id,
                key_prefix=f"rock_formula_{project_id}",
                identity_columns=[column for column in ("Rock", "Massif", "Lithology") if column in rock_source.columns],
            )
            rock_warnings = rock_source.attrs.get("user_derived_warnings", [])
            if rock_warnings:
                with st.expander(f"Предупреждения формул пород: {len(rock_warnings)}", expanded=False):
                    for warning in rock_warnings:
                        st.warning(str(warning))
        st.caption(
            "Нормированные REE/Spider отношения здесь намеренно не подменяются простой арифметикой: "
            "для них нужен явно выбранный reference (например, CI chondrite или primitive mantle)."
        )

    st.divider()
    render_section_header(
        "Структурные формулы минералов",
        "APFU, end-members и классификация сохраняются отдельным минералоспецифическим слоем.",
    )
    if not datasets or chosen is None or dataset_id is None:
        return
    if raw_source.empty:
        st.info("В выбранном наборе нет аналитических строк.")
        return

    selection_ids = _selection_ids_for_dataset(raw_source)
    apfu_source = raw_source
    selection_active = False
    if selection_ids:
        scope_label = st.segmented_control(
            "Какие точки пересчитывать",
            [f"Текущий отбор · {len(selection_ids)}", f"Весь набор · {len(raw_source)}"],
            default=f"Текущий отбор · {len(selection_ids)}",
            key=f"formula_scope_{dataset_id}",
            help="Selection задаёт только область APFU; пользовательские вычисляемые поля выше остаются свойством всего набора.",
        )
        selection_active = str(scope_label or "").startswith("Текущий отбор")
        if selection_active:
            wanted = set(selection_ids)
            apfu_source = raw_source[raw_source["_analysis_id"].astype(str).isin(wanted)].copy()
            st.success(f"APFU будет рассчитан только для текущего научного отбора: {len(apfu_source)} точек.")

    assigned_source = attach_mineral_assignments(
        apfu_source, default_mineral_key=str(chosen["mineral_key"])
    )
    mineral_choices = sorted(
        value for value in assigned_source["Минерал"].dropna().astype(str).unique() if value
    )
    if not mineral_choices:
        st.warning("В выбранных точках не удалось определить минералогическую группу для структурного пересчёта.")
        return
    target_mineral = st.selectbox(
        "Минерал для пересчёта",
        mineral_choices,
        index=mineral_choices.index(str(chosen["mineral_key"])) if str(chosen["mineral_key"]) in mineral_choices else 0,
        help="После переотнесения точка рассчитывается по новому минералу. Исходная химия и прежний расчёт сохраняются.",
    )
    source = assigned_source.loc[
        assigned_source["Минерал"].astype(str).eq(target_mineral)
    ].copy()
    point_specific = selection_active or len(source) != len(raw_source) or target_mineral != str(chosen["mineral_key"])
    if point_specific:
        st.info(
            f"В расчёт входит {len(source)} из {len(raw_source)} строк набора. APFU сохранится только для этих "
            "analysis_id; остальные строки не будут переопределены."
        )
    methods = methods_for(target_mineral)
    if not methods:
        st.warning(
            "Для этого минералогического модуля пока нет валидированного минералоспецифического пересчёта. "
            "Химия, назначение и QC остаются в базе; формулу не подставляем по аналогии."
        )
        return

    method_map = {method.id: method for method in methods}
    suggested = recommended_method(target_mineral)
    requested_method = st.session_state.pop("workflow_formula_method_id", None)
    default_method = requested_method if requested_method in method_map else (suggested.id if suggested else methods[0].id)
    method_id = st.selectbox(
        "Метод", list(method_map), index=list(method_map).index(default_method),
        format_func=lambda value: method_map[value].title_ru,
        key="formula_method",
    )
    method = method_map[method_id]
    if suggested and method_id == suggested.id:
        st.caption("Выбран рекомендуемый стартовый метод. Он не применяется автоматически: допущения остаются на вашем контроле.")
    with st.expander("Метод, допущения и источники", expanded=False):
        st.write(f"**Нормировка:** {method.normalization_ru}")
        st.write(f"**Допущения:** {method.assumptions_ru}")
        st.write("**Политика входов:** все распознанные измеренные oxide-columns участвуют в базовой формуле; фактический список сохраняется в provenance результата.")
        if method.warning_ru:
            st.warning(method.warning_ru)
        for reference in method.references:
            st.caption("• " + reference)

    try:
        result = calculate_formula_safe(source, target_mineral, method.id)
    except Exception as exc:
        st.error(f"Пересчёт остановлен: {exc}")
        return

    derived = _derived_columns(source, result.data)
    status = formula_status(dataset_id)
    status_badges = [
        (f"{len(source)} анализов в расчёте", "neutral"),
        (f"{len(derived)} расчётных полей", "accent"),
    ]
    if status.has_active_formula and status.method_id == method.id:
        status_badges.extend([
            (f"Актуально: {status.current_rows}/{status.total_rows}", "success" if status.stale_rows == 0 else "warning"),
            (f"Валидно: {status.valid_rows}", "success" if status.invalid_rows == 0 else "warning"),
            (f"Не рассчитано: {status.invalid_rows}", "warning" if status.invalid_rows else "neutral"),
        ])
        if status.unknown_validity_rows:
            status_badges.append((f"Старые результаты без validity: {status.unknown_validity_rows}", "warning"))
    else:
        status_badges.append(("○ Не сохранён для этого метода", "neutral"))
    render_badges(status_badges)

    if status.has_active_formula and status.method_id != method.id:
        st.caption(f"Сейчас активен другой метод: {status.method_title or status.method_id}.")
    if result.note_ru:
        st.caption(result.note_ru)
    if not derived:
        st.warning("Метод не создал новых расчётных колонок для этого набора.")
        return

    _render_full_validity_summary(result.data)
    _render_classification_summary(result.data)
    render_section_header("Результаты", "Предпросмотр первых 1000 строк текущей области расчёта")
    identity = _identity_columns(result.data)
    preview = result.data[identity + derived].copy()
    if "_analysis_id" in result.data.columns:
        preview.insert(0, "Точка", [human_point_label(row) for _, row in result.data.iterrows()])
    st.dataframe(preview.head(1000), width="stretch", hide_index=True, height=520)
    with st.expander("Исходные и расчётные данные вместе"):
        visible = [column for column in result.data.columns if not str(column).startswith("_")]
        full_view = result.data[visible].copy()
        if "_analysis_id" in result.data.columns:
            full_view.insert(0, "Точка", [human_point_label(row) for _, row in result.data.iterrows()])
        st.dataframe(full_view.head(500), width="stretch", hide_index=True, height=520)

    st.markdown('<div class="petrolab-export-zone"></div>', unsafe_allow_html=True)
    if st.button("Сохранить расчёт в рабочую базу", type="primary", key="save_formula_results", width="stretch"):
        saver = save_point_formula_results if point_specific else save_formula_results
        saved = saver(
            dataset_id=dataset_id,
            mineral_key=target_mineral,
            method_id=method.id,
            method_title=method.title_ru,
            source_dataframe=source,
            result_dataframe=result.data,
        )
        st.success(f"Сохранено {len(saved.derived_columns)} полей для {saved.row_count} анализов.")
        st.session_state["workflow_plot_dataset_ids"] = [dataset_id]
        st.session_state["workflow_plot_notice"] = "Расчёт сохранён. Текущий Selection останется подсвеченным на XY."
        st.session_state.pop("quick_plot_datasets", None)
        navigate("plots")
        st.rerun()

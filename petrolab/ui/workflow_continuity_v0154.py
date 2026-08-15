"""Связность сценария: импорт → фото → текстура → химия → Generation."""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import annotation_table
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.operation_journal import set_annotation_with_journal
from petrolab.term_registry import register_term, term_values
from petrolab.textural_runtime import (
    COMMON_TEXTURAL_ZONES,
    SOURCE_TEXTURAL_ZONE_COLUMN,
    TEXTURAL_ZONE_COLUMN,
)
from petrolab.ui import universal_intake as _universal
from petrolab.ui.image_components import SCOPE_LABELS
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project_id
from petrolab.ui.universal_intake_extensions import (
    _batch_token,
    render_image_wizard_multi_dataset as _base_image_wizard,
)


_PERSISTENT_CHEMICAL_SELECTION = "v0154_chemical_selection_ids"
_IGNORE_SELECTION_ONCE = "v0154_ignore_plot_selection_once"


def overlay_textural_zone(
    dataframe: pd.DataFrame,
    annotations: Mapping[str, Mapping[str, str]] | None = None,
) -> pd.DataFrame:
    """Показать ручную текстурную разметку поверх исходной, не уничтожая исходное значение."""
    result = dataframe.copy()
    if result.empty or "_analysis_id" not in result.columns:
        return result

    ids = result["_analysis_id"].astype(str).tolist()
    values = annotations if annotations is not None else annotation_table(ids, namespace="morphology")
    manual = pd.Series(
        [
            str(
                (values.get(analysis_id, {}) or {}).get("zone")
                or (values.get(analysis_id, {}) or {}).get("textural_role")
                or ""
            ).strip()
            for analysis_id in ids
        ],
        index=result.index,
        dtype="object",
    )
    has_manual = manual.astype(str).str.strip().ne("")
    if not bool(has_manual.any()):
        return result

    if TEXTURAL_ZONE_COLUMN in result.columns:
        if SOURCE_TEXTURAL_ZONE_COLUMN not in result.columns:
            result[SOURCE_TEXTURAL_ZONE_COLUMN] = result[TEXTURAL_ZONE_COLUMN].copy()
        source = result[TEXTURAL_ZONE_COLUMN].astype("string").fillna("")
        result[TEXTURAL_ZONE_COLUMN] = manual.where(has_manual, source)
    else:
        result[TEXTURAL_ZONE_COLUMN] = manual
    return result


def apply_persistent_selection_to_figure(figure, selected_ids: Iterable[str]):
    """Подсветить тот же набор analysis_id после смены осей или стиля графика."""
    wanted = {str(value).strip() for value in selected_ids if str(value).strip()}
    if not wanted:
        return figure

    traces: list[tuple[object, list[str]]] = []
    visible: set[str] = set()
    for trace in getattr(figure, "data", ()):
        customdata = getattr(trace, "customdata", None)
        if customdata is None:
            continue
        trace_ids: list[str] = []
        for row in customdata:
            if isinstance(row, (list, tuple)):
                analysis_id = row[0] if row else ""
            else:
                try:
                    analysis_id = row[0]
                except (IndexError, KeyError, TypeError):
                    analysis_id = row
            value = str(analysis_id).strip()
            trace_ids.append(value)
            if value:
                visible.add(value)
        traces.append((trace, trace_ids))

    if not (wanted & visible):
        return figure
    for trace, trace_ids in traces:
        trace.selectedpoints = [index for index, analysis_id in enumerate(trace_ids) if analysis_id in wanted]
    return figure


def _current_universal_import_ids(project_id: int) -> list[int]:
    accessible = {int(item["id"]) for item in list_accessible_datasets(int(project_id))}
    values: list[int] = []
    for key in list(st.session_state):
        if not str(key).startswith("universal_imported_"):
            continue
        for raw in st.session_state.get(key, []) or []:
            try:
                dataset_id = int(raw)
            except (TypeError, ValueError):
                continue
            if dataset_id in accessible and dataset_id not in values:
                values.append(dataset_id)
    return values


def _point_display(row: pd.Series) -> str:
    parts = [
        str(row.get("Sample") or "").strip(),
        str(row.get("Grain") or "").strip(),
        str(row.get("Point") or "").strip(),
    ]
    label = " · ".join(value for value in parts if value)
    analysis_id = str(row.get("_analysis_id") or "")
    return f"{label or 'точка'} · {analysis_id[:8]}"


def _render_current_image_textural_markup(
    project_id: int,
    image_files: list[tuple[str, bytes]],
) -> None:
    if not image_files:
        return
    batch = _batch_token(image_files)
    index = min(int(st.session_state.get(f"univimg_index_{batch}", 0)), len(image_files) - 1)
    name, raw = image_files[index]
    token = _universal._file_token(name, raw)
    prefix = f"univimg_{batch}_{token}"

    scope_label = st.session_state.get(f"{prefix}_scope", "К нескольким точкам анализа")
    if SCOPE_LABELS.get(scope_label) != "analysis":
        return
    dataset_id = st.session_state.get(f"{prefix}_dataset_id")
    if dataset_id is None:
        return
    try:
        dataset_id = int(dataset_id)
    except (TypeError, ValueError):
        return
    accessible = {int(item["id"]) for item in list_accessible_datasets(int(project_id))}
    if dataset_id not in accessible:
        return

    linked_ids = [
        str(value).strip()
        for value in st.session_state.get(f"{prefix}_analysis_ids", []) or []
        if str(value).strip()
    ]
    if not linked_ids:
        return

    dataframe = load_dataset_dataframe(dataset_id, include_meta=True)
    if dataframe.empty or "_analysis_id" not in dataframe.columns:
        return
    dataframe = dataframe.copy()
    dataframe["_analysis_id"] = dataframe["_analysis_id"].astype(str)
    allowed = set(dataframe["_analysis_id"].tolist())
    linked_ids = [analysis_id for analysis_id in linked_ids if analysis_id in allowed]
    if not linked_ids:
        return

    selected_rows = dataframe[dataframe["_analysis_id"].isin(linked_ids)].copy()
    labels = {
        str(row["_analysis_id"]): _point_display(row)
        for _, row in selected_rows.iterrows()
    }
    st.markdown("#### Первичная текстурная разметка текущего изображения")
    st.caption(
        "`Textural zone` — то, что вы наблюдаете на изображении: ядро, белая/серая кайма, "
        "реакционная зона и т. п. Это отдельно от `Generation`, которую позже можно утвердить по химии."
    )

    zone_ids = st.multiselect(
        "Какие из связанных точек относятся к одной текстурной зоне",
        linked_ids,
        default=linked_ids,
        format_func=lambda value: labels.get(str(value), str(value)),
        key=f"{prefix}_textural_zone_ids",
    )
    known = list(dict.fromkeys([
        *term_values(int(project_id), TEXTURAL_ZONE_COLUMN),
        *COMMON_TEXTURAL_ZONES,
    ]))
    choice = st.selectbox(
        "Текстурная зона",
        [*known, "Другое…"],
        key=f"{prefix}_textural_zone_choice",
    )
    if choice == "Другое…":
        zone = st.text_input(
            "Своё название",
            placeholder="например, тонкая внешняя кайма",
            key=f"{prefix}_textural_zone_custom",
        ).strip()
    else:
        zone = str(choice).strip()

    notice_key = f"{prefix}_textural_zone_notice"
    notice = st.session_state.pop(notice_key, "")
    if notice:
        st.success(str(notice))
    if st.button(
        "Назначить Textural zone выбранным точкам",
        type="primary",
        disabled=not zone_ids or not zone,
        width="stretch",
        key=f"{prefix}_save_textural_zone",
    ):
        count = set_annotation_with_journal(
            int(project_id),
            zone_ids,
            namespace="morphology",
            key="zone",
            value=zone,
            label=f"Текстурная зона → {zone}",
        )
        register_term(
            int(project_id),
            TEXTURAL_ZONE_COLUMN,
            zone,
            source="image_textural_zone",
        )
        st.session_state[notice_key] = f"Текстурная зона «{zone}» сохранена для {count} точек."
        st.rerun()

    current = annotation_table(linked_ids, namespace="morphology")
    status_rows: list[dict[str, str]] = []
    for _, row in selected_rows.iterrows():
        analysis_id = str(row["_analysis_id"])
        status_rows.append({
            "Точка": labels.get(analysis_id, analysis_id),
            "Textural zone": str((current.get(analysis_id, {}) or {}).get("zone") or ""),
        })
    if status_rows:
        st.dataframe(pd.DataFrame(status_rows), width="stretch", hide_index=True, height=min(260, 36 * len(status_rows) + 38))


def _render_image_wizard_with_textural_markup(
    project_id: int,
    image_files: list[tuple[str, bytes]],
    preferred_dataset_ids: list[int],
) -> None:
    # Разметка показывается до кнопки сохранения пачки на повторных рендерах,
    # когда пользователь уже выбрал связанные точки для текущего изображения.
    _render_current_image_textural_markup(int(project_id), image_files)
    _base_image_wizard(int(project_id), image_files, preferred_dataset_ids)


def _render_staging_textural_hint(original, *args, **kwargs):
    st.caption(
        "Для первичной петрографической разметки используйте `Textural zone` "
        "(ядро, белая кайма, серая кайма…). `Generation` лучше оставить для химической интерпретации."
    )
    return original(*args, **kwargs)


def _render_post_import_steps(project_id: int) -> None:
    dataset_ids = _current_universal_import_ids(int(project_id))
    if not dataset_ids:
        return
    st.divider()
    st.markdown("### Дальше по исследовательскому циклу")
    st.caption(
        "Если в пачке есть фотографии — сначала привяжите их выше и разметьте Textural zone. "
        "Затем откройте химию, выделите группы лассо/рамкой или статистикой и только после проверки утвердите Generation."
    )
    c1, c2, c3 = st.columns(3)
    if c1.button("Исследовать химию", type="primary", width="stretch", key="v0154_continue_chemistry"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        st.session_state["workflow_plot_notice"] = (
            "Открыты только что импортированные наборы. Текстурная зона доступна для группировки; "
            "рабочие химические группы можно выделять лассо или рамкой."
        )
        navigate("plots")
        st.rerun()
    if c2.button("Утвердить Generation", width="stretch", key="v0154_continue_generations"):
        navigate("generations")
        st.rerun()
    if c3.button("Сравнить с другими данными", width="stretch", key="v0154_continue_compare"):
        st.session_state["workflow_plot_dataset_ids"] = dataset_ids
        navigate("compare")
        st.rerun()


def render_add_data_page_v0154() -> None:
    """Добавить к staging фото-разметку и явное продолжение сценария."""
    from petrolab.ui import staged_intake as _staged_intake
    from petrolab.ui.pages import v0151_intake_wrappers as _base_page

    original_image_wizard = _base_page.render_image_wizard_multi_dataset
    original_staging = _staged_intake.render_staging_editor

    def staging_with_hint(*args, **kwargs):
        return _render_staging_textural_hint(original_staging, *args, **kwargs)

    _base_page.render_image_wizard_multi_dataset = _render_image_wizard_with_textural_markup
    _staged_intake.render_staging_editor = staging_with_hint
    try:
        _base_page.render_add_data_page()
    finally:
        _base_page.render_image_wizard_multi_dataset = original_image_wizard
        _staged_intake.render_staging_editor = original_staging

    project_id = active_project_id()
    if project_id is not None:
        _render_post_import_steps(int(project_id))


def _selected_ids_with_memory(original, event) -> list[str]:
    if st.session_state.pop(_IGNORE_SELECTION_ONCE, False):
        st.session_state.pop(_PERSISTENT_CHEMICAL_SELECTION, None)
        return []
    incoming = [str(value) for value in original(event) if str(value)]
    if incoming:
        st.session_state[_PERSISTENT_CHEMICAL_SELECTION] = list(dict.fromkeys(incoming))
    return [
        str(value)
        for value in st.session_state.get(_PERSISTENT_CHEMICAL_SELECTION, []) or []
        if str(value)
    ]


def _advanced_interactive_with_memory(original, xy_module, *args, **kwargs):
    persisted = [
        str(value)
        for value in st.session_state.get(_PERSISTENT_CHEMICAL_SELECTION, []) or []
        if str(value)
    ]
    if persisted:
        c1, c2 = st.columns([4, 1])
        c1.info(
            f"Текущий химический отбор: {len(persisted)} точек. Он сохраняется при смене X/Y, "
            "пока вы не сделаете новое выделение или не сбросите его."
        )
        if c2.button("Сбросить отбор", width="stretch", key="v0154_clear_chemical_selection"):
            st.session_state.pop(_PERSISTENT_CHEMICAL_SELECTION, None)
            st.session_state[_IGNORE_SELECTION_ONCE] = True
            st.session_state.pop("petrolab_advanced_interactive_plot", None)
            st.rerun()

    original_selected = xy_module.selected_analysis_ids
    original_build = xy_module.build_interactive_scatter

    def selected_with_memory(event):
        return _selected_ids_with_memory(original_selected, event)

    def build_with_memory(*build_args, **build_kwargs):
        figure = original_build(*build_args, **build_kwargs)
        selected = st.session_state.get(_PERSISTENT_CHEMICAL_SELECTION, []) or []
        return apply_persistent_selection_to_figure(figure, selected)

    xy_module.selected_analysis_ids = selected_with_memory
    xy_module.build_interactive_scatter = build_with_memory
    try:
        return original(*args, **kwargs)
    finally:
        xy_module.selected_analysis_ids = original_selected
        xy_module.build_interactive_scatter = original_build


def render_plots_page_v0154() -> None:
    """Сохранить химический отбор между осями и показать Textural zone на графиках."""
    from petrolab.ui import xy_components as _xy
    from petrolab.ui.pages import plots_advanced as _advanced
    from petrolab.ui.pages import plots_dashboard as _plots
    from petrolab.ui.pages import v0151_wrappers as _base_page

    original_quick_load = _plots.load_unified_with_derived
    original_advanced_load = _advanced.load_unified_with_derived
    original_advanced_interactive = _advanced.render_advanced_interactive

    def quick_load(project_id: int, dataset_ids):
        return overlay_textural_zone(original_quick_load(project_id, dataset_ids))

    def advanced_load(project_id: int, dataset_ids):
        return overlay_textural_zone(original_advanced_load(project_id, dataset_ids))

    def advanced_interactive(*args, **kwargs):
        return _advanced_interactive_with_memory(
            original_advanced_interactive,
            _xy,
            *args,
            **kwargs,
        )

    _plots.load_unified_with_derived = quick_load
    _advanced.load_unified_with_derived = advanced_load
    _advanced.render_advanced_interactive = advanced_interactive
    try:
        _base_page.render_plots_page()
    finally:
        _plots.load_unified_with_derived = original_quick_load
        _advanced.load_unified_with_derived = original_advanced_load
        _advanced.render_advanced_interactive = original_advanced_interactive

    st.divider()
    st.markdown("### После химической разметки")
    st.caption(
        "Лассо/рамка создают рабочие группы по immutable analysis_id. Когда группа проверена на разных осях, "
        "её можно утвердить как PetroLab Generation, не изменяя исходную Generation из файла или статьи."
    )
    if st.button("Перейти к поколениям", type="primary", width="stretch", key="v0154_plots_to_generations"):
        navigate("generations")
        st.rerun()


def render_multi_panel_page_v0154() -> None:
    """Показывать ручную Textural zone и при сравнении нескольких диаграмм."""
    from petrolab.ui.pages import multi_panel as _multi
    from petrolab.ui.pages import v0151_wrappers as _base_page

    original_raw = _multi._raw_dataframe

    def raw_with_texture(project_id: int):
        dataframe, dataset_ids = original_raw(project_id)
        return overlay_textural_zone(dataframe), dataset_ids

    _multi._raw_dataframe = raw_with_texture
    try:
        _base_page.render_multi_panel_page()
    finally:
        _multi._raw_dataframe = original_raw

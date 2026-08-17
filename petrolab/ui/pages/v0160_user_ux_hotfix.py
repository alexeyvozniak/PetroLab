from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from petrolab.analytical_sessions import annotation_table
from petrolab.dataframe_utils import compute_changes
from petrolab.db import META_COLUMNS, list_accessible_datasets
import petrolab.phase_suggestions as phase_suggestions
from petrolab.services.analysis_service import save_changes_and_sync, save_changes_to_database
from petrolab.ui import staged_intake, universal_intake, universal_intake_extensions
from petrolab.ui.editability import common_editable_source_columns
from petrolab.ui.layout import render_badges, render_section_header
from petrolab.ui.selection_context import read_selection

from . import add_data as _add
from . import mixed_minerals as _mixed
from . import object_workspace as _workspace
from . import plots_dashboard as _plots
from . import v0156_audit_wrappers as _audit_chain


_PHASE_OPTIONS = (
    "magnetite", "ilmenite", "spinel", "chromite", "magnesioferrite",
    "phlogopite", "biotite", "annite", "muscovite", "tetraferriphlogopite",
    "clinopyroxene", "diopside", "augite", "hedenbergite", "aegirine-augite", "aegirine",
    "amphibole", "kaersutite", "richterite", "hornblende", "arfvedsonite",
    "olivine", "forsterite", "fayalite",
    "garnet", "andradite", "melanite", "schorlomite", "grossular",
    "apatite", "perovskite", "titanite", "rutile", "zircon", "baddeleyite",
    "nepheline", "sodalite", "nosean", "leucite",
    "K-feldspar", "sanidine", "orthoclase", "albite", "plagioclase",
    "calcite", "dolomite", "ankerite", "siderite",
    "pyrochlore-supergroup", "pectolite", "wollastonite", "hydrogrossular",
    "Другая фаза…",
)


def compact_dataset_label(dataset: dict[str, Any]) -> str:
    """Put the useful scientific identity first; source/project context comes later."""
    name = str(dataset.get("name") or "").strip()
    source = str(dataset.get("source_filename") or "").strip()
    sheet = str(dataset.get("source_sheet") or "").strip()
    if not name:
        name = Path(source).stem if source else "Набор"

    parts = [name]
    if sheet and sheet.casefold() not in name.casefold():
        parts.append(sheet)
    mineral = str(dataset.get("mineral_key") or "").strip()
    if mineral and mineral != "generic":
        parts.append(mineral)
    rows = dataset.get("row_count")
    if rows is not None:
        parts.append(f"{int(rows)} строк")
    if source and source.casefold() not in name.casefold():
        parts.append(source)

    project = str(dataset.get("project_name") or "").strip()
    if project and project.casefold() not in {"общая база", "общая библиотека"}:
        parts.append(project)

    imported = dataset.get("imported_at")
    if imported:
        try:
            stamp = pd.to_datetime(imported, errors="raise")
            parts.append("импорт " + stamp.strftime("%d.%m.%Y %H:%M"))
        except (TypeError, ValueError, OverflowError):
            pass
    return " · ".join(part for part in parts if part)


def _manual_phase_key(label: str) -> str:
    text = str(label or "").strip().casefold()
    if any(token in text for token in ("magnet", "spinel", "chromit", "магнет", "шпинел", "хромит")):
        return "spinel"
    if "ilmen" in text or "ильмен" in text:
        return "fe_ti_oxide"
    if any(token in text for token in ("phlog", "biot", "annite", "muscov", "mica", "слюд", "флогоп", "биотит")):
        return "mica"
    if any(token in text for token in ("diop", "augite", "aegir", "hedenberg", "clinopyrox", "клинопирокс")):
        return "clinopyroxene"
    if any(token in text for token in ("amphib", "kaersut", "richter", "hornblend", "arfved", "амфиб")):
        return "amphibole"
    if any(token in text for token in ("andrad", "melanite", "schorl", "grossular", "garnet", "гранат")):
        return "garnet"
    if any(token in text for token in ("forster", "fayalit", "oliv", "олив")):
        return "olivine"
    if any(token in text for token in ("calcite", "dolomit", "anker", "sider", "carbonate", "кальцит", "доломит", "анкерит")):
        return "carbonate"
    if any(token in text for token in ("nephel", "sodal", "nosean", "leucit", "нефел", "содал", "нозеан")):
        return "feldspathoid"
    if any(token in text for token in ("sanidin", "orthoclas", "albite", "plagioclas", "feldspar", "санидин", "ортоклаз", "альбит")):
        return "feldspar"
    return phase_suggestions.mineral_key_for_phase(label)


def _sheet_multiselect_once(original):
    def wrapped(label, options, *args, **kwargs):
        key = str(kwargs.get("key") or "")
        option_list = list(options)
        if key.startswith("staging_sheets_"):
            kwargs.setdefault(
                "help",
                "Оставьте только те листы Excel, которые действительно хотите импортировать. Остальные листы файла не будут добавлены.",
            )
            return original("Какие листы добавить", option_list, *args, **kwargs)
        if key.startswith("universal_sheets_"):
            token = key.removeprefix("universal_sheets_")
            staged = st.session_state.get(f"staging_sheets_{token}")
            if isinstance(staged, (list, tuple)):
                selected = [value for value in staged if value in option_list]
                st.session_state[key] = selected
                return selected
        return original(label, option_list, *args, **kwargs)
    return wrapped


def _image_wizard_gate(original):
    def wrapped(project_id: int, image_files: list[tuple[str, bytes]], preferred_dataset_ids: list[int]) -> None:
        if not image_files:
            return
        batch = universal_intake_extensions._batch_token(image_files)
        key = f"intake_image_step_open_{batch}"
        if not bool(st.session_state.get(key, False)):
            st.divider()
            render_section_header(
                "2. Изображения",
                f"Таблица готова. Следующий шаг — разметить {len(image_files)} изображений и привязать их к точкам.",
            )
            if st.button(
                f"Дальше → разметить изображения · {len(image_files)}",
                type="primary",
                width="stretch",
                key=f"intake_open_images_{batch}",
            ):
                st.session_state[key] = True
                st.rerun()
            return
        original(int(project_id), image_files, preferred_dataset_ids)
    return wrapped


def render_add_data_page() -> None:
    """Remove duplicated workbook controls and make the image step explicit."""
    original_multiselect = st.multiselect
    original_inner_provenance = staged_intake.render_table_import_with_provenance
    original_image_wizard = universal_intake_extensions.render_image_wizard_multi_dataset

    st.multiselect = _sheet_multiselect_once(original_multiselect)
    staged_intake.render_table_import_with_provenance = (
        lambda original, project_id, name, data, token: original(project_id, name, data, token)
    )
    universal_intake_extensions.render_image_wizard_multi_dataset = _image_wizard_gate(original_image_wizard)
    try:
        _add.render_add_data_page()
    finally:
        st.multiselect = original_multiselect
        staged_intake.render_table_import_with_provenance = original_inner_provenance
        universal_intake_extensions.render_image_wizard_multi_dataset = original_image_wizard


def _render_inline_workspace_editor(
    dataframe: pd.DataFrame,
    *,
    project_id: int | None,
    key_prefix: str,
    height: int,
) -> pd.DataFrame:
    if project_id is None or dataframe.empty or "_analysis_id" not in dataframe.columns:
        st.info("Для правки нужен активный проект и аналитические строки.")
        return dataframe

    datasets = list_accessible_datasets(int(project_id))
    selected_ids = sorted({
        int(value) for value in dataframe.get("_dataset_id", pd.Series(dtype=int)).dropna().tolist()
    })
    editable = common_editable_source_columns(datasets, selected_ids)
    visible = [column for column in dataframe.columns if not str(column).startswith("_")]
    internals = [column for column in dataframe.columns if str(column).startswith("_")]
    base = dataframe[[*internals, *visible]].copy()
    protected = (set(base.columns) - set(editable)) | META_COLUMNS | {column for column in base.columns if str(column).startswith("_")}
    disabled = [column for column in base.columns if column in protected]

    selection = read_selection()
    render_badges([
        (f"Selection · {selection.count}", "accent" if selection.count else "neutral"),
        (f"редактируемых полей · {len(editable)}", "success" if editable else "warning"),
    ])
    if not editable:
        st.warning(
            "У выбранных наборов нет общего безопасно редактируемого исходного поля. "
            "Сузьте рабочий контекст до одного набора или наборов с одинаковой схемой."
        )
        return dataframe

    st.caption(
        "Двойной щелчок по разрешённой ячейке — правка. Служебные, расчётные и derived-поля заблокированы. "
        "Изменения попадают в базу только после кнопки «Сохранить»."
    )
    editor_key = f"{key_prefix}_inline_editor"
    edited = st.data_editor(
        base,
        width="stretch",
        hide_index=True,
        height=height,
        disabled=disabled,
        num_rows="fixed",
        key=editor_key,
    )
    changes = compute_changes(base, edited, protected_columns=protected)
    if changes:
        render_badges([(f"несохранённых изменений · {len(changes)}", "warning")])

    save, sync = st.columns(2)
    if save.button(
        "Сохранить",
        type="primary",
        disabled=not changes,
        width="stretch",
        key=f"{key_prefix}_inline_save",
    ):
        result = save_changes_to_database(changes)
        if result.ok:
            st.session_state.pop(editor_key, None)
            st.session_state[f"{key_prefix}_inline_flash"] = f"Сохранено изменений: {result.saved_changes}."
            st.rerun()
        for error in result.errors:
            st.error(error)
    if sync.button(
        "Сохранить + обновить связанный Excel",
        disabled=not changes,
        width="stretch",
        key=f"{key_prefix}_inline_sync",
    ):
        result = save_changes_and_sync(changes)
        if result.ok:
            st.session_state.pop(editor_key, None)
            st.session_state[f"{key_prefix}_inline_flash"] = (
                f"Сохранено: {result.saved_changes}; обновлено файлов: {result.synced_files}."
            )
            st.rerun()
        for error in result.errors:
            st.error(error)

    flash = st.session_state.pop(f"{key_prefix}_inline_flash", "")
    if flash:
        st.success(str(flash))
    return dataframe


def render_object_workspace_page() -> None:
    """Keep Excel-like selection and direct editing in the same Workspace page."""
    original_table = _workspace.render_analysis_table

    def workspace_table(dataframe, *, project_id, key_prefix, height=560):
        mode = st.segmented_control(
            "Работа с таблицей",
            ["Выбирать", "Править"],
            default="Выбирать",
            key=f"{key_prefix}_interaction_mode",
            help=(
                "«Выбирать» — протянуть мышью диапазон и работать с Selection. "
                "«Править» — менять значения прямо в ячейках этой же рабочей таблицы."
            ),
        ) or "Выбирать"
        if mode == "Править":
            return _render_inline_workspace_editor(
                dataframe,
                project_id=project_id,
                key_prefix=key_prefix,
                height=height,
            )
        return original_table(
            dataframe,
            project_id=project_id,
            key_prefix=key_prefix,
            height=height,
        )

    _workspace.render_analysis_table = workspace_table
    try:
        _audit_chain.render_object_workspace_page()
    finally:
        _workspace.render_analysis_table = original_table


def _preferred_mixed_dataset_id(datasets: list[dict[str, Any]], current: Any = None) -> int | None:
    by_id = {int(item["id"]): item for item in datasets}
    try:
        current_id = int(current)
    except (TypeError, ValueError):
        current_id = None
    if current_id in by_id:
        return current_id
    for item in datasets:
        name = str(item.get("name") or "").casefold()
        if str(item.get("mineral_key") or "") == "generic" or "mixed" in name or "неразобран" in name:
            return int(item["id"])
    return int(datasets[0]["id"]) if datasets else None


def _phase_review_editor(original):
    def wrapped(data, *args, **kwargs):
        if not isinstance(data, pd.DataFrame) or "Подтверждённая фаза" not in data.columns or "Подтвердить" not in data.columns:
            return original(data, *args, **kwargs)

        frame = data.copy()
        if "_analysis_id" in frame.columns:
            ids = frame["_analysis_id"].astype(str).tolist()
            confirmed = annotation_table(ids, namespace="phase")
            for index, analysis_id in zip(frame.index, ids):
                value = str((confirmed.get(analysis_id, {}) or {}).get("confirmed_phase") or "").strip()
                if value:
                    frame.at[index, "Подтверждённая фаза"] = value

        key = str(kwargs.get("key") or "mixed_review")
        overrides_key = f"{key}_bulk_phase_overrides"
        overrides = st.session_state.get(overrides_key, {})
        if isinstance(overrides, dict) and "_analysis_id" in frame.columns:
            for index, analysis_id in zip(frame.index, frame["_analysis_id"].astype(str)):
                if analysis_id in overrides:
                    frame.at[index, "Подтверждённая фаза"] = str(overrides[analysis_id])
                    frame.at[index, "Подтвердить"] = True

        edited = original(frame, *args, **kwargs)
        st.markdown("##### Быстро назначить фазу")
        st.caption(
            "Отметьте нужные строки в колонке «В минерал», выберите фазу из словаря и примените её ко всем отмеченным. "
            "Для редкого минерала выберите «Другая фаза…»."
        )
        choice = st.selectbox("Фаза", _PHASE_OPTIONS, key=f"{key}_phase_picker")
        custom = ""
        if choice == "Другая фаза…":
            custom = st.text_input("Название фазы", key=f"{key}_phase_custom").strip()
        phase = custom if choice == "Другая фаза…" else str(choice)
        all_rows = st.checkbox(
            "Применить ко всем показанным строкам",
            key=f"{key}_phase_all_rows",
            help="Полезно, если весь текущий фильтр — одна и та же фаза.",
        )
        if st.button(
            "Назначить фазу",
            type="primary",
            disabled=not phase,
            key=f"{key}_phase_apply",
        ):
            mask = pd.Series(True, index=edited.index) if all_rows else edited["Подтвердить"].fillna(False).astype(bool)
            selected_ids = (
                edited.loc[mask, "_analysis_id"].astype(str).tolist()
                if "_analysis_id" in edited.columns else []
            )
            if not selected_ids:
                st.warning("Сначала отметьте строки в колонке «В минерал» или включите «ко всем показанным».")
            else:
                stored = dict(overrides) if isinstance(overrides, dict) else {}
                for analysis_id in selected_ids:
                    stored[str(analysis_id)] = phase
                st.session_state[overrides_key] = stored
                st.rerun()
        return edited
    return wrapped


def render_mixed_minerals_page() -> None:
    """Respect manual phase decisions and keep the user on the remaining mixed dataset."""
    project_id = _audit_chain.active_project_id()
    if project_id is not None:
        datasets = list_accessible_datasets(int(project_id))
        recent = st.session_state.pop("workflow_recent_mixed_dataset_id", None)
        explicit = st.session_state.get("workflow_mixed_dataset_id")
        preferred = _preferred_mixed_dataset_id(datasets, recent if recent is not None else explicit)
        if preferred is not None:
            st.session_state["workflow_mixed_dataset_id"] = int(preferred)

    original_editor = st.data_editor
    original_phase_key = phase_suggestions.mineral_key_for_phase
    original_mixed_phase_key = _mixed.mineral_key_for_phase

    def phase_key(label: str) -> str:
        return _manual_phase_key(label)

    st.data_editor = _phase_review_editor(original_editor)
    phase_suggestions.mineral_key_for_phase = phase_key
    _mixed.mineral_key_for_phase = phase_key
    try:
        _audit_chain.render_mixed_minerals_page()
    finally:
        st.data_editor = original_editor
        phase_suggestions.mineral_key_for_phase = original_phase_key
        _mixed.mineral_key_for_phase = original_mixed_phase_key


def render_plots_page() -> None:
    """Show the dataset itself first and expose the full chosen labels below the selector."""
    original_label = _plots.dataset_label
    original_multiselect = st.multiselect

    def multiselect_with_full_choice(label, options, *args, **kwargs):
        result = original_multiselect(label, options, *args, **kwargs)
        if str(kwargs.get("key") or "") == "quick_plot_datasets" and result:
            shown = [str(value) for value in result]
            text = " | ".join(shown[:4]) + (f" | ещё {len(shown) - 4}" if len(shown) > 4 else "")
            st.caption("Выбрано: " + text)
        return result

    _plots.dataset_label = compact_dataset_label
    st.multiselect = multiselect_with_full_choice
    try:
        _plots.render_plots_dashboard_page()
    finally:
        _plots.dataset_label = original_label
        st.multiselect = original_multiselect

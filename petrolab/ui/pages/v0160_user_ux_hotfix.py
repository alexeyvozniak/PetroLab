from __future__ import annotations

import json
from collections import Counter
from typing import Any

import pandas as pd
import streamlit as st

import petrolab.phase_suggestions as phase_suggestions
from petrolab.analytical_sessions import set_annotations
from petrolab.dataframe_utils import dataset_label as _legacy_dataset_label
from petrolab.db import (
    get_dataset,
    list_accessible_datasets,
    load_dataset_dataframe,
    update_analysis_values,
)
from petrolab.mineral_recognition_extended import MINERAL_KEYS
from petrolab.operation_journal import journaled_operation
from petrolab.oxide_mineral_recognition import OXIDE_MINERAL_KEYS
from petrolab.ui import staged_intake
from petrolab.ui.layout import render_badges, render_section_header
from petrolab.ui.navigation import navigate
from petrolab.ui.selection_context import read_selection, set_selection

from . import mixed_minerals as _mixed
from . import object_workspace as _workspace
from . import plots_dashboard as _plots
from . import v0156_audit_wrappers as _audit_chain


_RECOGNITION_LABELS: dict[str, str] = {
    "generic": "Не определено",
    "mica": "mica / слюда",
    "phlogopite": "phlogopite / флогопит",
    "biotite": "biotite / биотит",
    "muscovite": "muscovite / мусковит",
    "clinopyroxene": "clinopyroxene / клинопироксен",
    "diopside": "diopside / диопсид",
    "augite": "augite / авгит",
    "aegirine": "aegirine / эгирин",
    "amphibole": "amphibole / амфибол",
    "kaersutite": "kaersutite / керсутит",
    "richterite": "richterite / рихтерит",
    "garnet": "garnet / гранат",
    "andradite": "andradite / андрадит",
    "melanite": "melanite / меланит",
    "olivine": "olivine / оливин",
    "spinel": "spinel / шпинель",
    "magnetite": "magnetite / магнетит",
    "chromite": "chromite / хромит",
    "fe_ti_oxide": "Fe-Ti oxide / Fe-Ti оксид",
    "ilmenite": "ilmenite / ильменит",
    "perovskite": "perovskite / перовскит",
    "rutile": "rutile / рутил",
    "titanite": "titanite / титанит",
    "apatite": "apatite / апатит",
    "zircon": "zircon / циркон",
    "carbonate": "carbonate / карбонат",
    "calcite": "calcite / кальцит",
    "dolomite": "dolomite / доломит",
    "feldspar": "feldspar / полевой шпат",
    "orthoclase": "orthoclase / ортоклаз",
    "sanidine": "sanidine / санидин",
    "plagioclase": "plagioclase / плагиоклаз",
    "feldspathoid": "feldspathoid / фельдшпатоид",
    "nepheline": "nepheline / нефелин",
    "sodalite": "sodalite / содалит",
    "nosean": "nosean / нозеан",
    "pectolite": "pectolite / пектолит",
    "hydrogrossular": "hydrogrossular / гидрогроссуляр",
}

_PHASE_OPTIONS = list(dict.fromkeys([
    "phlogopite", "biotite", "muscovite", "mica",
    "clinopyroxene", "diopside", "augite", "aegirine",
    "amphibole", "kaersutite", "richterite",
    "garnet", "andradite", "melanite", "olivine",
    "magnetite", "chromite", "spinel", "ilmenite", "fe_ti_oxide",
    "perovskite", "rutile", "titanite", "apatite", "zircon",
    "carbonate", "calcite", "dolomite",
    "feldspar", "orthoclase", "sanidine", "plagioclase",
    "feldspathoid", "nepheline", "sodalite", "nosean",
    "pectolite", "hydrogrossular",
    *MINERAL_KEYS,
    *OXIDE_MINERAL_KEYS,
]))


def compact_dataset_label(item: dict[str, Any]) -> str:
    """Put the useful dataset/sheet identity before long source/project names."""
    name = str(item.get("name") or f"Набор {item.get('id', '—')}").strip()
    sheet = str(item.get("source_sheet") or "").strip()
    source = str(item.get("source_filename") or "").strip()
    count = int(item.get("row_count") or 0)
    pieces = [name]
    if sheet and sheet.casefold() not in name.casefold():
        pieces.append(sheet)
    if source and source.casefold() not in " · ".join(pieces).casefold():
        pieces.append(source)
    return " · ".join(pieces) + f" · {count} точек"


def _image_wizard_gate(original):
    """After table import make image markup an explicit next step instead of continuing below silently."""
    def wrapped(project_id: int, image_files: list[tuple[str, bytes]], preferred_dataset_ids: list[int]) -> None:
        if not image_files:
            return
        token = "|".join(name for name, _ in image_files)
        gate_key = f"v0160_image_gate_{hash(token)}"
        if not st.session_state.get(gate_key):
            st.divider()
            render_section_header(
                "Следующий шаг · изображения",
                "Таблица уже проверена. Теперь можно по очереди привязать фотографии к Sample / Point / точным analysis_id.",
            )
            if st.button(
                f"Дальше → разметить изображения · {len(image_files)}",
                type="primary",
                width="stretch",
                key=f"{gate_key}_button",
            ):
                st.session_state[gate_key] = True
                st.rerun()
            return
        original(int(project_id), image_files, preferred_dataset_ids)
    return wrapped


def render_add_data_page() -> None:
    original = _audit_chain.universal_intake_extensions.render_image_wizard_multi_dataset
    _audit_chain.universal_intake_extensions.render_image_wizard_multi_dataset = _image_wizard_gate(original)
    try:
        _audit_chain.render_add_data_page()
    finally:
        _audit_chain.universal_intake_extensions.render_image_wizard_multi_dataset = original


def _editable_columns(dataframe: pd.DataFrame) -> list[str]:
    locked = {"_analysis_id", "_dataset_id", "_source_row", "_source_sheet", "_source_filename", "_source_sha256"}
    return [column for column in dataframe.columns if column not in locked and not str(column).startswith("apfu_")]


def _render_editable_workspace(dataframe: pd.DataFrame) -> None:
    if dataframe.empty or "_analysis_id" not in dataframe.columns or "_dataset_id" not in dataframe.columns:
        st.info("Для правки нужны аналитические строки с устойчивыми analysis_id.")
        return
    editable = _editable_columns(dataframe)
    if not editable:
        st.info("В текущем представлении нет редактируемых исходных колонок.")
        return
    columns = ["_analysis_id", "_dataset_id", *editable]
    original = dataframe[columns].copy()
    edited = st.data_editor(
        original,
        width="stretch",
        hide_index=True,
        disabled=["_analysis_id", "_dataset_id"],
        key="workspace_cell_editor",
    )
    changes: list[dict[str, Any]] = []
    for index in original.index:
        analysis_id = str(original.at[index, "_analysis_id"])
        dataset_id = int(original.at[index, "_dataset_id"])
        for column in editable:
            old = original.at[index, column]
            new = edited.at[index, column]
            same = (pd.isna(old) and pd.isna(new)) or old == new
            if bool(same):
                continue
            changes.append({
                "analysis_id": analysis_id,
                "dataset_id": dataset_id,
                "column_name": str(column),
                "old_value": old,
                "new_value": new,
            })
    if not changes:
        st.caption("Двойной клик по ячейке → исправить значение. Служебные ID и расчётные apfu заблокированы.")
        return
    render_badges([(f"изменений · {len(changes)}", "warning")])
    if st.button("Сохранить правки", type="primary", width="stretch", key="workspace_save_cells"):
        with journaled_operation(
            "analyses.bulk_cell_edit",
            target_ids=[str(item["analysis_id"]) for item in changes],
            label=f"Правка ячеек · {len(changes)}",
            metadata={"columns": sorted({str(item["column_name"]) for item in changes})},
        ):
            update_analysis_values(changes)
        st.success(f"Сохранено изменений: {len(changes)}.")
        st.rerun()


def render_object_workspace_page() -> None:
    """Keep multi-cell selection and direct editing in one Workspace page."""
    original_dataframe = st.dataframe

    mode = st.segmented_control(
        "Работа с таблицей",
        ["Выбирать", "Править"],
        default="Выбирать",
        key="workspace_table_mode",
        help="«Выбирать» — протянуть мышью как в Excel. «Править» — изменить значения в ячейках и сохранить с журналом.",
    ) or "Выбирать"

    if mode == "Править":
        captured: dict[str, pd.DataFrame] = {}

        def capture_dataframe(data, *args, **kwargs):
            if isinstance(data, pd.DataFrame) and "_analysis_id" in data.columns and "_dataset_id" in data.columns:
                captured["data"] = data.copy()
            return original_dataframe(data, *args, **kwargs)

        st.dataframe = capture_dataframe
        try:
            _workspace.render_object_workspace_page()
        finally:
            st.dataframe = original_dataframe
        if "data" in captured:
            st.divider()
            render_section_header("Править данные", "Изменения записываются по analysis_id и попадают в журнал операций")
            _render_editable_workspace(captured["data"])
        return

    _workspace.render_object_workspace_page()


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


def _phase_review_editor(original_editor):
    def wrapped(data, *args, **kwargs):
        key = str(kwargs.get("key") or "")
        if "phase_review_editor" not in key or not isinstance(data, pd.DataFrame):
            return original_editor(data, *args, **kwargs)
        frame = data.copy()
        current = [str(value or "").strip() for value in frame.get("Подтверждённая фаза", pd.Series("", index=frame.index))]
        if "Подтверждённая фаза" in frame.columns:
            config = dict(kwargs.get("column_config") or {})
            options = ["", *_PHASE_OPTIONS, "Другая фаза…"]
            config["Подтверждённая фаза"] = st.column_config.SelectboxColumn(
                "Подтверждённая фаза",
                options=options,
                format_func=lambda value: _RECOGNITION_LABELS.get(str(value), str(value)),
                help="Ручное решение имеет приоритет над новым автоматическим предположением.",
            )
            kwargs["column_config"] = config
        edited = original_editor(frame, *args, **kwargs)

        if "Подтверждённая фаза" in edited.columns and "_analysis_id" in edited.columns:
            overrides_key = f"{key}_manual_custom"
            overrides = st.session_state.get(overrides_key, {})
            selected_custom = edited["Подтверждённая фаза"].astype(str).eq("Другая фаза…")
            if selected_custom.any():
                custom = st.text_input(
                    "Другая фаза",
                    placeholder="например, baddeleyite, cancrinite, pectolite",
                    key=f"{key}_custom_phase_name",
                ).strip()
                selected_ids = edited.loc[selected_custom, "_analysis_id"].astype(str).tolist()
                if st.button(
                    f"Применить «{custom or 'другая фаза'}» к {len(selected_ids)}",
                    disabled=not custom,
                    key=f"{key}_apply_custom_phase",
                    width="stretch",
                ):
                    stored = dict(overrides) if isinstance(overrides, dict) else {}
                    for analysis_id in selected_ids:
                        stored[str(analysis_id)] = custom
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
        key = str(kwargs.get("key") or "")
        if key and key in st.session_state and "default" in kwargs:
            kwargs = dict(kwargs)
            kwargs.pop("default", None)
        result = original_multiselect(label, options, *args, **kwargs)
        if key == "quick_plot_datasets" and result:
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
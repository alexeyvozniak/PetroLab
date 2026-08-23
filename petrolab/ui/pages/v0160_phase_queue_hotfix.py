from __future__ import annotations

from collections import defaultdict
from typing import Any

import streamlit as st

from petrolab.analytical_sessions import set_annotations
from petrolab.db import connect, list_accessible_datasets, unlink_dataset_from_project
import petrolab.phase_suggestions as _phase_suggestions
from petrolab.phase_suggestions import _move_rows_to_dataset, _reindex_dataset_rows
from petrolab.ui.layout import render_badges, render_section_header
from petrolab.ui.project_context import active_project_id

from . import mixed_minerals as _mixed
from . import v0156_audit_wrappers as _audit_chain
from . import v0160_user_ux_hotfix as _ux_chain


_REVIEWED_KEY = "_phase_review_completed_dataset_ids"
_BASE_MINERAL_KEY_FOR_PHASE = _phase_suggestions.mineral_key_for_phase
_SPLIT_STATE_SUFFIXES = (
    " · Неразобранные / mixed",
    " · Исходный mixed (разобрано)",
)


def _phase_dataset_root_name(value: Any) -> str:
    """Return the stable scientific dataset name without transient mixed-state suffixes."""
    clean = str(value or "").strip()
    changed = True
    while changed:
        changed = False
        for suffix in _SPLIT_STATE_SUFFIXES:
            if clean.endswith(suffix):
                clean = clean[: -len(suffix)].rstrip()
                changed = True
    return clean


def _reviewable(dataset: dict[str, Any]) -> bool:
    """Only raw/mixed rows belong to the normal phase-review queue."""
    if int(dataset.get("row_count") or 0) <= 0:
        return False
    name = str(dataset.get("name") or "").casefold()
    mineral = str(dataset.get("mineral_key") or "").strip().casefold()
    return mineral == "generic" or "нераспознан" in name or "неразобран" in name or "mixed" in name


def _ordered_candidates(
    datasets: list[dict[str, Any]],
    *,
    completed: set[int],
    after_dataset_id: int | None = None,
) -> list[dict[str, Any]]:
    candidates = [item for item in datasets if _reviewable(item) and int(item["id"]) not in completed]
    if not candidates:
        return []

    by_id = {int(item["id"]): item for item in datasets}
    current = by_id.get(int(after_dataset_id)) if after_dataset_id is not None else None
    if current is None:
        return sorted(candidates, key=lambda item: (str(item.get("source_filename") or ""), int(item["id"])))

    source_hash = str(current.get("source_sha256") or "")
    source_file = str(current.get("source_filename") or "")
    current_id = int(current["id"])
    same_book = [
        item for item in candidates
        if str(item.get("source_sha256") or "") == source_hash
        and str(item.get("source_filename") or "") == source_file
    ]
    later = sorted((item for item in same_book if int(item["id"]) > current_id), key=lambda item: int(item["id"]))
    earlier = sorted((item for item in same_book if int(item["id"]) <= current_id), key=lambda item: int(item["id"]))
    other = sorted(
        (item for item in candidates if item not in same_book),
        key=lambda item: (str(item.get("source_filename") or ""), int(item["id"])),
    )
    return [*later, *earlier, *other]


def _nested_split_pairs(datasets: list[dict[str, Any]]) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Find children accidentally split again from an already resolved phase dataset."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for item in datasets:
        signature = (str(item.get("source_sha256") or ""), str(item.get("source_sheet") or ""))
        groups[signature].append(item)

    result: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for siblings in groups.values():
        for child in siblings:
            child_root = _phase_dataset_root_name(child.get("name"))
            parents = [
                parent for parent in siblings
                if int(parent["id"]) != int(child["id"])
                and child_root.startswith(_phase_dataset_root_name(parent.get("name")) + " · ")
                and str(parent.get("mineral_key") or "generic") != "generic"
            ]
            if not parents:
                continue
            parent = max(
                parents,
                key=lambda item: len(_phase_dataset_root_name(item.get("name"))),
            )
            result.append((child, parent))
    return sorted(
        result,
        key=lambda pair: len(_phase_dataset_root_name(pair[0].get("name"))),
        reverse=True,
    )


def _repair_nested_splits(project_id: int, pairs: list[tuple[dict[str, Any], dict[str, Any]]]) -> tuple[int, int]:
    moved = 0
    hidden = 0
    repaired_children: set[int] = set()
    annotation_updates: list[tuple[list[str], str]] = []

    # First move rows in one SQLite transaction. Do not open a second writer while
    # this transaction is active: on Windows that can produce "database is locked".
    with connect() as con:
        for child, parent in pairs:
            child_id = int(child["id"])
            parent_id = int(parent["id"])
            rows = con.execute(
                "SELECT analysis_id FROM analysis_rows WHERE dataset_id=? ORDER BY row_index",
                (child_id,),
            ).fetchall()
            analysis_ids = [str(row["analysis_id"]) for row in rows]
            if analysis_ids:
                _move_rows_to_dataset(con, child_id, parent_id, analysis_ids)
                _reindex_dataset_rows(con, child_id)
                parent_root = _phase_dataset_root_name(parent.get("name"))
                parent_phase = parent_root.rsplit(" · ", 1)[-1].strip() if " · " in parent_root else ""
                if parent_phase:
                    annotation_updates.append((analysis_ids, parent_phase))
                moved += len(analysis_ids)
            repaired_children.add(child_id)
        con.commit()

    # The row move is now committed; annotation repair can safely use its own connection.
    for analysis_ids, parent_phase in annotation_updates:
        set_annotations(
            analysis_ids,
            {"confirmed_phase": parent_phase},
            namespace="phase",
            source="manual_repair",
        )

    for child_id in repaired_children:
        unlink_dataset_from_project(int(project_id), int(child_id))
        hidden += 1
    return moved, hidden


def _render_repeat_split_cleanup(project_id: int, datasets: list[dict[str, Any]]) -> None:
    pairs = _nested_split_pairs(datasets)
    if not pairs:
        return
    st.warning(
        f"Обнаружены повторно разобранные фазовые наборы: {len(pairs)}. "
        "Это похоже на цикл, когда уже созданная фаза снова попадала в «Фазы и выбросы»."
    )
    with st.expander("Исправить наборы, созданные повторным разбором", expanded=False):
        for child, parent in pairs[:20]:
            st.caption(f"{child.get('name')} → вернуть точки в {parent.get('name')}")
        if len(pairs) > 20:
            st.caption(f"Ещё: {len(pairs) - 20}")
        confirm = st.checkbox(
            "Вернуть точки в их предыдущие фазовые наборы и убрать лишние дочерние наборы из проекта",
            key="phase_repair_nested_confirm",
        )
        if st.button(
            "Исправить повторные разбиения",
            type="primary",
            disabled=not confirm,
            width="stretch",
            key="phase_repair_nested_apply",
        ):
            moved, hidden = _repair_nested_splits(int(project_id), pairs)
            st.session_state["phase_repair_flash"] = (
                f"Исправлено: возвращено точек {moved}; лишних наборов убрано из проекта {hidden}. "
                "Сами анализы не удалялись."
            )
            st.rerun()


def _safe_manual_phase_key(label: str) -> str:
    """Use the UX aliases without recursing after the underlying mapper is monkey-patched."""
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
    return _BASE_MINERAL_KEY_FOR_PHASE(label)


def render_mixed_minerals_page() -> None:
    """Review each raw/mixed dataset once, then advance to the next sheet."""
    project_id = active_project_id()
    if project_id is None:
        _ux_chain.render_mixed_minerals_page()
        return
    project_id = int(project_id)

    datasets = list_accessible_datasets(project_id)
    flash = st.session_state.pop("phase_repair_flash", "")
    if flash:
        st.success(str(flash))
    _render_repeat_split_cleanup(project_id, datasets)

    completed_raw = st.session_state.get(_REVIEWED_KEY, [])
    completed: set[int] = set()
    for value in completed_raw if isinstance(completed_raw, (list, tuple, set)) else []:
        try:
            completed.add(int(value))
        except (TypeError, ValueError):
            continue

    just_finished = st.session_state.pop("workflow_recent_mixed_dataset_id", None)
    finished_id: int | None = None
    if just_finished is not None:
        try:
            finished_id = int(just_finished)
        except (TypeError, ValueError):
            finished_id = None
        if finished_id is not None:
            completed.add(finished_id)
            st.session_state[_REVIEWED_KEY] = sorted(completed)
            st.session_state.pop("mixed_dataset", None)

    candidates = _ordered_candidates(datasets, completed=completed, after_dataset_id=finished_id)
    if not candidates:
        _mixed._recent_split_actions(project_id)
        render_section_header("Разбор фаз завершён", "В текущем проходе больше нет сырых/mixed-наборов с точками")
        st.success("PetroLab не будет снова предлагать уже разобранные фазовые наборы.")
        st.caption(
            "Если вы намеренно хотите вернуться к остаткам mixed-набора, начните новый проход. "
            "Готовые фазовые наборы при этом не попадут в обычную очередь."
        )
        if st.button("Начать новый проход по оставшимся mixed-наборам", width="stretch", key="phase_review_restart"):
            st.session_state[_REVIEWED_KEY] = []
            st.rerun()
        return

    next_id = int(candidates[0]["id"])
    st.session_state["workflow_mixed_dataset_id"] = next_id
    render_badges([
        (f"в очереди · {len(candidates)}", "accent"),
        ("готовые фазы исключены из очереди", "success"),
    ])
    if finished_id is not None:
        st.success("Предыдущий набор сохранён. Открыт следующий ещё не разобранный лист/набор.")

    filtered = list(candidates)

    def filtered_datasets(_project_id: int):
        return list(filtered)

    original_mixed_list = _mixed.list_accessible_datasets
    original_audit_list = _audit_chain.list_accessible_datasets
    original_ux_list = _ux_chain.list_accessible_datasets
    original_manual_phase_key = _ux_chain._manual_phase_key
    _mixed.list_accessible_datasets = filtered_datasets
    _audit_chain.list_accessible_datasets = filtered_datasets
    _ux_chain.list_accessible_datasets = filtered_datasets
    _ux_chain._manual_phase_key = _safe_manual_phase_key
    try:
        _ux_chain.render_mixed_minerals_page()
    finally:
        _mixed.list_accessible_datasets = original_mixed_list
        _audit_chain.list_accessible_datasets = original_audit_list
        _ux_chain.list_accessible_datasets = original_ux_list
        _ux_chain._manual_phase_key = original_manual_phase_key

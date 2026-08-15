from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import pandas as pd
import streamlit as st

from petrolab.import_staging import (
    ROLE_ALIASES,
    SimilarName,
    apply_block_fill,
    assign_value_to_rows,
    detect_block_header_rows,
    detect_role_columns,
    name_similarity,
    normalized_name_key,
    similar_name_candidates,
)
from petrolab.ui.layout import render_badges, render_hint, render_section_header


# One canonical vocabulary powers automatic detection and manual assignment. Adding a
# role to ROLE_ALIASES therefore makes it available everywhere in staging.
CANONICAL_STAGE_FIELDS = tuple(ROLE_ALIASES)


@dataclass(frozen=True)
class StagingResult:
    dataframe: pd.DataFrame
    role_columns: dict[str, str]
    sample_column: str | None
    source_column: str | None


def _state_key(token: str, sheet: str) -> str:
    return f"staging_frame_{token}_{sheet}"


def _signature_key(token: str, sheet: str) -> str:
    return f"staging_source_signature_{token}_{sheet}"


def _selection_key(token: str, sheet: str) -> str:
    return f"staging_selection_{token}_{sheet}"


def _source_signature(dataframe: pd.DataFrame) -> tuple[int, tuple[str, ...]]:
    return len(dataframe), tuple(str(column) for column in dataframe.columns)


def _reset_frame(token: str, sheet: str, dataframe: pd.DataFrame) -> pd.DataFrame:
    st.session_state[_state_key(token, sheet)] = dataframe.copy()
    st.session_state[_signature_key(token, sheet)] = _source_signature(dataframe)
    st.session_state.pop(_selection_key(token, sheet), None)
    return dataframe.copy()


def _current_frame(token: str, sheet: str, dataframe: pd.DataFrame) -> pd.DataFrame:
    key = _state_key(token, sheet)
    signature = _source_signature(dataframe)
    if st.session_state.get(_signature_key(token, sheet)) != signature:
        return _reset_frame(token, sheet, dataframe)
    stored = st.session_state.get(key)
    if not isinstance(stored, pd.DataFrame):
        return _reset_frame(token, sheet, dataframe)
    return stored.copy()


def _role_mapping_controls(frame: pd.DataFrame, token: str, sheet: str) -> dict[str, str]:
    detected = detect_role_columns(frame.columns)
    options = ["—"] + [str(column) for column in frame.columns]
    mapping: dict[str, str] = {}
    with st.expander("Что означает каждый столбец", expanded=False):
        render_hint(
            "PetroLab предлагает роли по русским и английским заголовкам без учёта регистра. "
            "Любое соответствие можно изменить до импорта."
        )
        columns = st.columns(2)
        for index, role in enumerate(CANONICAL_STAGE_FIELDS):
            suggestion = detected.get(role)
            choice = columns[index % 2].selectbox(
                role,
                options,
                index=options.index(suggestion) if suggestion in options else 0,
                key=f"staging_role_{token}_{sheet}_{role}",
                help="; ".join(ROLE_ALIASES.get(role, ())),
            )
            if choice != "—":
                mapping[role] = choice
    return mapping


def _row_selector(frame: pd.DataFrame, token: str, sheet: str) -> list[int]:
    if frame.empty:
        return []
    mode = st.segmented_control(
        "Какие строки изменить",
        ["Диапазон", "Отметить строки", "Весь лист"],
        default="Диапазон",
        key=f"staging_select_mode_{token}_{sheet}",
    ) or "Диапазон"
    if mode == "Весь лист":
        return list(range(len(frame)))
    if mode == "Диапазон":
        left, right = st.columns(2)
        start = int(left.number_input("С строки", 1, len(frame), 1, key=f"staging_start_{token}_{sheet}"))
        stop = int(right.number_input("По строку", 1, len(frame), min(len(frame), start), key=f"staging_stop_{token}_{sheet}"))
        lo, hi = sorted((start, stop))
        return list(range(lo - 1, hi))

    visible = frame.head(3000).copy()
    visible.insert(0, "Выбрать", False)
    edited = st.data_editor(
        visible,
        hide_index=True,
        width="stretch",
        height=340,
        disabled=[column for column in visible.columns if column != "Выбрать"],
        column_config={"Выбрать": st.column_config.CheckboxColumn("✓")},
        key=_selection_key(token, sheet),
    )
    if len(frame) > 3000:
        st.warning("Для ручного выбора показаны первые 3000 строк; для длинных таблиц используйте диапазон.")
    return [
        position
        for position, selected in enumerate(edited["Выбрать"].fillna(False).astype(bool).tolist())
        if selected
    ]


def _mass_assignment(frame: pd.DataFrame, token: str, sheet: str) -> pd.DataFrame:
    render_section_header("Ручная адаптация", "Одно значение можно назначить сразу любому диапазону строк")
    selected = _row_selector(frame, token, sheet)
    render_badges([(f"выбрано · {len(selected)}", "accent" if selected else "neutral")])
    left, right = st.columns(2)
    field_mode = left.selectbox(
        "Поле",
        [*CANONICAL_STAGE_FIELDS, "Пользовательское поле…"],
        key=f"staging_field_mode_{token}_{sheet}",
    )
    field = field_mode
    if field_mode == "Пользовательское поле…":
        field = left.text_input("Название нового поля", key=f"staging_custom_field_{token}_{sheet}").strip()
    value = right.text_input("Значение", key=f"staging_value_{token}_{sheet}")
    if st.button(
        "Применить к выбранным строкам",
        type="primary",
        disabled=not selected or not field or not value.strip(),
        key=f"staging_apply_{token}_{sheet}",
        width="stretch",
    ):
        frame = assign_value_to_rows(frame, selected, field=field, value=value.strip())
        st.session_state[_state_key(token, sheet)] = frame
        st.success(f"{field} = {value.strip()} применено к {len(selected)} строкам.")
        st.rerun()
    return frame


def _block_assistant(frame: pd.DataFrame, token: str, sheet: str, chemistry_columns: Iterable[str]) -> pd.DataFrame:
    suggestions = detect_block_header_rows(frame, chemistry_columns=chemistry_columns)
    if not suggestions:
        return frame
    with st.expander(f"Похожие на заголовки блоков строки · {len(suggestions)}", expanded=False):
        st.caption(
            "Например, строка `19KL23` перед серией анализов. Ничего не протягивается вниз без подтверждения."
        )
        preview = pd.DataFrame([{"Строка": pos + 1, "Значение": value} for pos, value in suggestions[:100]])
        st.dataframe(preview, hide_index=True, width="stretch", height=min(300, 44 + 34 * len(preview)))
        options = ["Sample", "Lithology", "Source", "Locality", "Massif", "Generation", "Игнорировать"]
        field = st.selectbox("Что означают эти заголовки", options, key=f"staging_block_field_{token}_{sheet}")
        if field != "Игнорировать" and st.button(
            "Протянуть заголовки вниз до следующего блока",
            key=f"staging_block_apply_{token}_{sheet}",
            width="stretch",
        ):
            frame = apply_block_fill(frame, dict(suggestions), field=field, drop_header_rows=True)
            st.session_state[_state_key(token, sheet)] = frame
            st.success(f"Заголовки перенесены в {field}; строки-заголовки исключены из аналитических строк.")
            st.rerun()
    return frame


def _similarity_reason(left: str, right: str) -> str:
    if left.casefold() == right.casefold():
        return "отличается только регистром"
    if normalized_name_key(left) == normalized_name_key(right):
        return "совпадает после нормализации/транслитерации"
    return "похожее написание"


def _intra_file_candidates(values: list[str], threshold: float = 0.82) -> list[SimilarName]:
    ordered: list[str] = []
    for value in values:
        if value and value not in ordered:
            ordered.append(value)
    result: list[SimilarName] = []
    for index, incoming in enumerate(ordered):
        scored = [
            (name_similarity(incoming, previous), previous)
            for previous in ordered[:index]
            if previous != incoming
        ]
        if not scored:
            continue
        score, canonical = max(scored)
        if score >= threshold:
            result.append(SimilarName(incoming, canonical, float(score), _similarity_reason(incoming, canonical)))
    return result


def _duplicate_reconciliation(
    frame: pd.DataFrame,
    *,
    field: str,
    existing_names: Iterable[str],
    token: str,
    sheet: str,
) -> dict[str, str]:
    if field not in frame.columns:
        return {}
    incoming = [str(value).strip() for value in frame[field].dropna().tolist() if str(value).strip()]
    candidates = [*similar_name_candidates(incoming, existing_names), *_intra_file_candidates(incoming)]
    grouped: dict[str, dict[str, SimilarName]] = {}
    for item in candidates:
        grouped.setdefault(item.incoming, {})[item.existing] = item
    if not grouped:
        return {}

    resolved: dict[str, str] = {}
    with st.expander(f"Похожие названия · {field} · {len(grouped)}", expanded=True):
        st.caption(
            "Регистр, транслитерация и похожее написание используются только для поиска кандидатов. "
            "PetroLab не объединяет похожие научные объекты без вашего подтверждения."
        )
        for index, (incoming_name, by_existing) in enumerate(grouped.items()):
            found = sorted(by_existing.values(), key=lambda item: (-item.score, item.existing.casefold()))
            choices = ["— оставить отдельным —", *[item.existing for item in found]]
            choice = st.selectbox(
                f"{incoming_name} похоже на…",
                choices,
                key=f"staging_dup_{token}_{sheet}_{field}_{index}",
                help=" · ".join(f"{item.existing}: {item.reason}, {item.score:.0%}" for item in found[:5]),
            )
            if choice != "— оставить отдельным —":
                resolved[incoming_name] = choice
    return resolved


def render_staging_editor(
    dataframe: pd.DataFrame,
    *,
    token: str,
    sheet: str,
    chemistry_columns: Iterable[str] = (),
    existing_samples: Iterable[str] = (),
    existing_sources: Iterable[str] = (),
) -> tuple[StagingResult, dict[str, str], dict[str, str]]:
    frame = _current_frame(token, sheet, dataframe)
    render_section_header("Предпросмотр до импорта", "Автоматика сначала; ручные изменения касаются только staging-копии")
    role_columns = _role_mapping_controls(frame, token, sheet)
    frame = _block_assistant(frame, token, sheet, chemistry_columns)
    frame = _mass_assignment(frame, token, sheet)

    if st.button("Сбросить ручную адаптацию этого листа", key=f"staging_reset_{token}_{sheet}"):
        _reset_frame(token, sheet, dataframe)
        st.rerun()

    st.dataframe(frame.head(100), width="stretch", hide_index=True, height=min(500, 45 + 32 * min(100, len(frame))))
    if len(frame) > 100:
        st.caption(f"Показаны первые 100 из {len(frame)} строк staging-копии.")

    sample_column = role_columns.get("Sample") or ("Sample" if "Sample" in frame.columns else None)
    source_column = role_columns.get("Source") or ("Source" if "Source" in frame.columns else None)
    sample_confirmations = _duplicate_reconciliation(
        frame,
        field=sample_column or "Sample",
        existing_names=existing_samples,
        token=token,
        sheet=sheet,
    )
    source_confirmations = _duplicate_reconciliation(
        frame,
        field=source_column or "Source",
        existing_names=existing_sources,
        token=token,
        sheet=sheet,
    )
    return StagingResult(frame, role_columns, sample_column, source_column), sample_confirmations, source_confirmations

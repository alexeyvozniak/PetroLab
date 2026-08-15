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


CANONICAL_STAGE_FIELDS = (
    "Sample", "Lithology", "Source", "Mineral", "Generation", "Grain", "Point", "Method", "Locality", "Massif",
)


@dataclass(frozen=True)
class StagingResult:
    dataframe: pd.DataFrame
    role_columns: dict[str, str]
    sample_column: str | None
    source_column: str | None


def _state_key(token: str, sheet: str) -> str:
    return f"staging_frame_{token}_{sheet}"


def _selection_key(token: str, sheet: str) -> str:
    return f"staging_selection_{token}_{sheet}"


def _reset_frame(token: str, sheet: str, dataframe: pd.DataFrame) -> pd.DataFrame:
    key = _state_key(token, sheet)
    st.session_state[key] = dataframe.copy()
    st.session_state.pop(_selection_key(token, sheet), None)
    return st.session_state[key]


def _current_frame(token: str, sheet: str, dataframe: pd.DataFrame) -> pd.DataFrame:
    key = _state_key(token, sheet)
    stored = st.session_state.get(key)
    if not isinstance(stored, pd.DataFrame) or list(stored.columns) != list(dataframe.columns) or len(stored) != len(dataframe):
        st.session_state[key] = dataframe.copy()
    return st.session_state[key].copy()


def _role_mapping_controls(frame: pd.DataFrame, token: str, sheet: str) -> dict[str, str]:
    detected = detect_role_columns(frame.columns)
    options = ["—"] + [str(column) for column in frame.columns]
    role_columns: dict[str, str] = {}
    with st.expander("Что означает каждый столбец", expanded=False):
        render_hint(
            "PetroLab предлагает роли по русским и английским заголовкам без учёта регистра. "
            "Вы можете изменить любое соответствие до импорта."
        )
        columns = st.columns(2)
        for index, role in enumerate(CANONICAL_STAGE_FIELDS):
            suggested = detected.get(role)
            default = options.index(suggested) if suggested in options else 0
            choice = columns[index % 2].selectbox(
                role,
                options,
                index=default,
                key=f"staging_role_{token}_{sheet}_{role}",
                help="; ".join(ROLE_ALIASES.get(role, ())),
            )
            if choice != "—":
                role_columns[role] = choice
    return role_columns


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
        c1, c2 = st.columns(2)
        start = int(c1.number_input("С строки", 1, max(1, len(frame)), 1, key=f"staging_start_{token}_{sheet}"))
        stop = int(c2.number_input("По строку", 1, max(1, len(frame)), min(len(frame), start), key=f"staging_stop_{token}_{sheet}"))
        lo, hi = sorted((start, stop))
        return list(range(lo - 1, hi))

    visible = frame.head(3000).copy()
    visible.insert(0, "Выбрать", False)
    editor = st.data_editor(
        visible,
        hide_index=True,
        width="stretch",
        height=340,
        disabled=[column for column in visible.columns if column != "Выбрать"],
        column_config={"Выбрать": st.column_config.CheckboxColumn("✓")},
        key=_selection_key(token, sheet),
    )
    if len(frame) > 3000:
        st.warning("Для ручного выбора показаны первые 3000 строк; используйте диапазон для более длинных таблиц.")
    return [int(position) for position, selected in enumerate(editor["Выбрать"].fillna(False).astype(bool).tolist()) if selected]


def _mass_assignment(frame: pd.DataFrame, token: str, sheet: str) -> pd.DataFrame:
    render_section_header("Ручная адаптация", "Любое метаполе можно назначить сразу диапазону строк до импорта")
    selected_rows = _row_selector(frame, token, sheet)
    render_badges([(f"выбрано · {len(selected_rows)}", "accent" if selected_rows else "neutral")])
    c1, c2 = st.columns([1, 1])
    field_mode = c1.selectbox(
        "Поле",
        [*CANONICAL_STAGE_FIELDS, "Пользовательское поле…"],
        key=f"staging_field_mode_{token}_{sheet}",
    )
    field = field_mode
    if field_mode == "Пользовательское поле…":
        field = c1.text_input("Название нового поля", key=f"staging_custom_field_{token}_{sheet}").strip()
    value = c2.text_input("Значение", key=f"staging_value_{token}_{sheet}")
    if st.button(
        "Применить к выбранным строкам",
        type="primary",
        disabled=not selected_rows or not field or not value.strip(),
        key=f"staging_apply_{token}_{sheet}",
        width="stretch",
    ):
        frame = assign_value_to_rows(frame, selected_rows, field=field, value=value.strip())
        st.session_state[_state_key(token, sheet)] = frame
        st.success(f"{field} = {value.strip()} применено к {len(selected_rows)} строкам.")
        st.rerun()
    return frame


def _block_assistant(frame: pd.DataFrame, token: str, sheet: str, chemistry_columns: Iterable[str]) -> pd.DataFrame:
    suggestions = detect_block_header_rows(frame, chemistry_columns=chemistry_columns)
    if not suggestions:
        return frame
    with st.expander(f"Похожие на заголовки блоков строки · {len(suggestions)}", expanded=False):
        st.caption(
            "Например, строка `19KL23` перед серией химических анализов. Ничего не распространяется вниз без подтверждения."
        )
        preview = pd.DataFrame(
            [{"Строка": position + 1, "Значение": value} for position, value in suggestions[:100]],
        )
        st.dataframe(preview, hide_index=True, width="stretch", height=min(300, 44 + 34 * len(preview)))
        field = st.selectbox(
            "Что означают эти заголовки",
            ["Sample", "Lithology", "Source", "Locality", "Massif", "Generation", "Игнорировать"],
            key=f"staging_block_field_{token}_{sheet}",
        )
        if field != "Игнорировать" and st.button(
            "Протянуть заголовки вниз до следующего блока",
            key=f"staging_block_apply_{token}_{sheet}",
            width="stretch",
        ):
            frame = apply_block_fill(frame, dict(suggestions), field=field, drop_header_rows=True)
            st.session_state[_state_key(token, sheet)] = frame
            st.success(f"Подтверждённые заголовки перенесены в поле {field}; строки-заголовки исключены из анализов.")
            st.rerun()
    return frame


def _reason(left: str, right: str) -> str:
    if left.casefold() == right.casefold():
        return "отличается только регистром"
    if normalized_name_key(left) == normalized_name_key(right):
        return "совпадает после нормализации/транслитерации"
    return "похожее написание"


def _intra_file_candidates(incoming: list[str], threshold: float = 0.82) -> list[SimilarName]:
    ordered: list[str] = []
    for value in incoming:
        if value and value not in ordered:
            ordered.append(value)
    result: list[SimilarName] = []
    for index, candidate in enumerate(ordered):
        previous = ordered[:index]
        if not previous:
            continue
        scored = sorted(
            ((name_similarity(candidate, current), current) for current in previous if current != candidate),
            reverse=True,
        )
        if not scored or scored[0][0] < threshold:
            continue
        score, canonical = scored[0]
        result.append(SimilarName(candidate, canonical, float(score), _reason(candidate, canonical)))
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
    if not candidates:
        return {}

    grouped: dict[str, list[SimilarName]] = {}
    for item in candidates:
        items = grouped.setdefault(item.incoming, [])
        if not any(existing.existing == item.existing for existing in items):
            items.append(item)
    resolved: dict[str, str] = {}
    with st.expander(f"Похожие названия · {field} · {len(grouped)}", expanded=True):
        st.caption(
            "Регистр и русско-английская транслитерация учитываются при поиске. "
            "Похожие научные объекты не объединяются молча — подтвердите совпадение. "
            "Проверяются и уже существующая база, и дубли внутри этого файла."
        )
        for index, (incoming_name, options_found) in enumerate(grouped.items()):
            options_found = sorted(options_found, key=lambda item: (-item.score, item.existing.casefold()))
            labels = ["— оставить отдельным —", *[item.existing for item in options_found]]
            choice = st.selectbox(
                f"{incoming_name} похоже на…",
                labels,
                key=f"staging_dup_{token}_{sheet}_{field}_{index}",
                help=" · ".join(
                    f"{item.existing}: {item.reason}, {item.score:.0%}" for item in options_found[:5]
                ),
            )
            if choice != "— оставить отдельным —":
                resolved[incoming_name] = choice
        if len(grouped) > 50:
            st.caption("Кандидатов много: после подтверждения одинаковые варианты будут сведены до импорта.")
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
    render_section_header("Предпросмотр до импорта", "Автоматика сначала; ручные исправления применяются только к staging-копии")
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
        frame, field=sample_column or "Sample", existing_names=existing_samples, token=token, sheet=sheet,
    )
    source_confirmations = _duplicate_reconciliation(
        frame, field=source_column or "Source", existing_names=existing_sources, token=token, sheet=sheet,
    )
    return (
        StagingResult(frame, role_columns, sample_column, source_column),
        sample_confirmations,
        source_confirmations,
    )

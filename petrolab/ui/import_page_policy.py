from __future__ import annotations

from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.column_schema import CANONICAL_ROLES
from petrolab.minerals.registry import MINERALS

ROLE_LABELS = {
    "Sample": "Образец", "Grain": "Зерно", "Point": "Точка анализа",
    "Generation": "Генерация / группа кристаллизации",
}
FE_OPTIONS = {
    "FeO": {
        "FeO = отдельно заданное Fe²⁺": "FeO",
        "FeO = всё Fe, выраженное как FeO total": "FeOt",
    },
    "Fe2O3": {
        "Fe₂O₃ = отдельно заданное Fe³⁺": "Fe2O3",
        "Fe₂O₃ = всё Fe, выраженное как Fe₂O₃ total": "Fe2O3t",
    },
}


def _sheet_settings(selected, default_header: int, default_mineral: str, prefix: str):
    header_rows: dict[str, int] = {}
    mineral_keys: dict[str, str] = {}
    if len(selected) > 1:
        st.caption("У каждого выбранного листа можно задать собственный минерал и строку заголовков.")
    for index, sheet in enumerate(selected):
        label = sheet or "CSV"
        with st.expander(f"Настройки листа: {label}", expanded=index == 0 and len(selected) > 1):
            c1, c2 = st.columns(2)
            header_rows[sheet] = int(c1.number_input(
                "Строка заголовков", 1, 200, int(default_header), 1,
                key=f"{prefix}_header_{index}",
            ))
            mineral_keys[sheet] = c2.selectbox(
                "Минерал", list(MINERALS),
                index=list(MINERALS).index(default_mineral),
                format_func=lambda key: MINERALS[key].name_ru,
                key=f"{prefix}_mineral_{index}",
            )
    return header_rows, mineral_keys


def _schema_mapping(selected, inspector, prefix: str, header_rows: dict[str, int]):
    semantic_maps: dict[str, dict[str, str]] = {}
    measurement_maps: dict[str, dict[str, str]] = {}
    ready = True
    if not selected:
        return semantic_maps, measurement_maps, ready

    st.subheader("Сопоставление колонок")
    st.caption(
        "Оксиды и элементы с единицами нормализуются автоматически. Неоднозначные роли и "
        "способ представления железа подтверждаются отдельно для каждого листа."
    )
    for sheet_index, sheet in enumerate(selected):
        label = sheet or "CSV"
        try:
            preview = inspector(sheet, header_rows[sheet])
        except Exception as exc:
            st.error(f"{label}: не удалось прочитать заголовки — {exc}")
            ready = False
            continue

        with st.expander(f"Колонки: {label}", expanded=sheet_index == 0):
            changed = [
                {"В Excel": original, "В ПетроЛабе": normalized}
                for original, normalized in preview.source_headers if original != normalized
            ]
            if changed:
                st.dataframe(pd.DataFrame(changed), width="stretch", hide_index=True)
            if preview.measurement_notes:
                for note in preview.measurement_notes:
                    st.caption("• " + note)
            if preview.duplicate_canonical_columns:
                st.error(
                    "Конфликтующие колонки после нормализации: "
                    + ", ".join(preview.duplicate_canonical_columns)
                    + ". Импорт этого листа заблокирован до исправления исходной таблицы."
                )
                ready = False

            measurement: dict[str, str] = {}
            for source in ("FeO", "Fe2O3"):
                if source not in preview.schema.columns:
                    continue
                options = FE_OPTIONS[source]
                choice = st.radio(
                    f"Что означает {source} на этом листе?",
                    list(options), index=None,
                    key=f"{prefix}_{source}_semantics_{sheet_index}",
                )
                if choice is None:
                    ready = False
                    st.caption("Нужно подтвердить смысл этой колонки перед импортом.")
                else:
                    measurement[source] = options[choice]
            measurement_maps[sheet] = measurement

            options = ["—"] + [
                column for column in preview.schema.columns
                if column not in {"Σ оксидов", "QC суммы", "QC железа", "QC химии"}
            ]
            semantic: dict[str, str] = {}
            cols = st.columns(2)
            for role_index, role in enumerate(CANONICAL_ROLES):
                suggestion = preview.schema.suggested.get(role)
                default_index = options.index(suggestion) if suggestion in options else 0
                value = cols[role_index % 2].selectbox(
                    ROLE_LABELS[role], options, index=default_index,
                    key=f"{prefix}_schema_{sheet_index}_{role}",
                )
                if value != "—":
                    semantic[role] = value
                weak = preview.schema.weak_candidates.get(role, ())
                if weak and not suggestion:
                    cols[role_index % 2].caption(
                        "Возможный кандидат: " + ", ".join(weak) + ". Подтвердите вручную."
                    )
            semantic_maps[sheet] = semantic
    return semantic_maps, measurement_maps, ready


def _render_linked_import(target, project_id: int) -> None:
    st.subheader("Связать локальный файл")
    path_text = st.text_input("Полный путь к Excel/CSV", key="local_source_path")
    default_header = int(st.number_input(
        "Строка заголовков по умолчанию", 1, 200, 1, 1, key="local_header_row"
    ))
    if not path_text.strip():
        return
    try:
        source_path = Path(path_text).expanduser()
        sheets = target.list_linked_sheets(source_path)
    except Exception as exc:
        st.error(f"Не удалось открыть источник: {exc}")
        return

    suffix = source_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        st.info("XLSX/XLSM: доступна двусторонняя синхронизация с проверкой внешних изменений.")
    else:
        st.info("XLS/CSV: файл можно импортировать и перечитывать, но обратная запись в источник отключена.")

    selected = st.multiselect("Листы для импорта", sheets, default=sheets[:1], key="linked_sheets")
    default_mineral = st.selectbox(
        "Минерал по умолчанию", list(MINERALS),
        format_func=lambda key: MINERALS[key].name_ru, key="linked_mineral"
    )
    dataset_name = st.text_input("Название набора", value=source_path.stem, key="linked_dataset_name")
    headers, minerals = _sheet_settings(selected, default_header, default_mineral, "linked")
    semantic, measurement, ready = _schema_mapping(
        selected,
        lambda sheet, header: target.inspect_linked_sheet(source_path, sheet, header),
        "linked", headers,
    )

    if selected and ready:
        try:
            sheet = selected[0]
            preview = target.preview_linked_source(
                source_path, sheet, headers[sheet], minerals[sheet],
                semantic.get(sheet, {}), measurement.get(sheet, {}),
            )
            st.subheader("Предпросмотр после нормализации")
            st.dataframe(preview.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Не удалось построить предпросмотр: {exc}")
            ready = False

    if st.button("Связать и импортировать", type="primary", key="link_local", disabled=not selected or not ready):
        try:
            result = target.import_linked_sheets(
                project_id=project_id, path=source_path, sheet_names=selected,
                mineral_key=default_mineral, dataset_name=dataset_name, header_row=default_header,
                semantic_maps=semantic, measurement_maps=measurement,
                header_rows=headers, mineral_keys=minerals,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать источник: {exc}")


def _render_uploaded_import(target, project_id: int) -> None:
    st.subheader("Импорт через браузер")
    uploaded = st.file_uploader("Excel или CSV", type=["xlsx", "xlsm", "xls", "csv"], key="upload_source")
    if uploaded is None:
        return
    data = uploaded.getvalue()
    default_header = int(st.number_input(
        "Строка заголовков по умолчанию", 1, 200, 1, 1, key="upload_header_row"
    ))
    try:
        sheets = target.list_uploaded_sheets(data, uploaded.name)
    except Exception as exc:
        st.error(f"Не удалось открыть загруженный файл: {exc}")
        return
    selected = st.multiselect("Листы для импорта", sheets, default=sheets[:1], key="upload_sheets")
    default_mineral = st.selectbox(
        "Минерал по умолчанию", list(MINERALS),
        format_func=lambda key: MINERALS[key].name_ru, key="upload_mineral"
    )
    dataset_name = st.text_input("Название набора", value=Path(uploaded.name).stem, key="upload_dataset_name")
    headers, minerals = _sheet_settings(selected, default_header, default_mineral, "upload")
    semantic, measurement, ready = _schema_mapping(
        selected,
        lambda sheet, header: target.inspect_uploaded_sheet(data, uploaded.name, sheet, header),
        "upload", headers,
    )
    if selected and ready:
        try:
            sheet = selected[0]
            preview = target.preview_uploaded_source(
                data, uploaded.name, sheet, headers[sheet], minerals[sheet],
                semantic.get(sheet, {}), measurement.get(sheet, {}),
            )
            st.subheader("Предпросмотр после нормализации")
            st.dataframe(preview.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"Не удалось построить предпросмотр: {exc}")
            ready = False
    if st.button("Импортировать рабочую копию", type="primary", key="upload_import", disabled=not selected or not ready):
        try:
            result = target.import_uploaded_sheets(
                project_id=project_id, file_bytes=data, filename=uploaded.name,
                sheet_names=selected, mineral_key=default_mineral, dataset_name=dataset_name,
                header_row=default_header, semantic_maps=semantic, measurement_maps=measurement,
                header_rows=headers, mineral_keys=minerals,
            )
            st.success(f"Импортировано наборов: {result.count}.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось импортировать рабочую копию: {exc}")


def install() -> None:
    from petrolab.ui.pages import sources as target

    target._render_linked_import = lambda project_id: _render_linked_import(target, project_id)
    target._render_uploaded_import = lambda project_id: _render_uploaded_import(target, project_id)

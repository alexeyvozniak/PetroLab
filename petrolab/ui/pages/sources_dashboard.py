from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

from petrolab.column_schema import CANONICAL_ROLES
from petrolab.db import (
    get_or_create_library_project,
    link_dataset_to_project,
    list_accessible_datasets,
    list_datasets,
)
from petrolab.io_utils import sha256_file
from petrolab.minerals.registry import MINERALS
from petrolab.formula_workflow import recommended_method
from petrolab.services.import_service import (
    ImportSchemaPreview,
    import_linked_sheets,
    import_uploaded_sheets,
    inspect_linked_sheet,
    inspect_linked_block,
    inspect_uploaded_sheet,
    inspect_uploaded_block,
    list_linked_sheets,
    list_uploaded_sheets,
    preview_linked_source,
    preview_linked_block,
    preview_uploaded_source,
    preview_uploaded_block,
    refresh_dataset_from_source,
)
from petrolab.sources import source_status
from petrolab.ui.layout import render_badges, render_hint, render_page_header, render_work_context
from petrolab.ui.navigation import navigate
from petrolab.ui.project_context import active_project


ROLE_LABELS = {
    "Sample": "Образец",
    "Grain": "Зерно",
    "Point": "Точка анализа",
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


def _import_mineral_keys() -> list[str]:
    """Put the scientifically safe mixed/unknown mode first only in the import workflow."""
    return ["generic", *[key for key in MINERALS if key != "generic"]]


def _import_mineral_label(key: str) -> str:
    if key == "generic":
        return "Смешанный / определить автоматически"
    return MINERALS[key].name_ru


def _continue_after_import(dataset_ids: list[int], project_id: int) -> None:
    """Attach fresh global data to this project and persist the next-step prompt."""
    for dataset_id in dataset_ids:
        link_dataset_to_project(
            int(project_id), int(dataset_id),
            "Добавлено при импорте в рабочий проект", purpose="working",
        )
    st.session_state["workflow_recent_dataset_ids"] = [int(value) for value in dataset_ids]
    st.session_state["workflow_recent_import_target"] = int(project_id)
    st.rerun()


def _import_target(active_project_id: int, key: str) -> int:
    """All raw imports are global; the active project receives a reference after save."""
    del active_project_id, key
    st.caption(
        "Будет создан новый набор в **Общей базе** и сразу добавлен в текущий проект. "
        "Проект хранит подборку, графики и интерпретации, а не дубликат химии."
    )
    return get_or_create_library_project()


def _render_import_continue(project_id: int) -> None:
    dataset_ids = [int(value) for value in st.session_state.get("workflow_recent_dataset_ids", [])]
    datasets = {int(item["id"]): item for item in list_accessible_datasets(project_id)}
    dataset_ids = [value for value in dataset_ids if value in datasets]
    if not dataset_ids:
        return
    st.success(f"Импортировано наборов: {len(dataset_ids)}.")
    st.caption("Следующий шаг можно сделать сейчас или вернуться к нему позже — исходные данные уже сохранены.")
    if len(dataset_ids) == 1:
        dataset = datasets[dataset_ids[0]]
        if str(dataset["mineral_key"]) == "generic":
            if st.button("Разобрать фазы и выбросы", type="primary", key="import_to_phases", width="stretch"):
                st.session_state["workflow_mixed_dataset_id"] = int(dataset["id"])
                navigate("mixed_minerals")
                st.rerun()
        elif recommended_method(str(dataset["mineral_key"])):
            if st.button("Проверить формулу и APFU", type="primary", key="import_to_formula", width="stretch"):
                st.session_state["workflow_formula_dataset_id"] = int(dataset["id"])
                st.session_state.pop("formula_dataset", None)
                st.session_state.pop("formula_method", None)
                suggested = recommended_method(str(dataset["mineral_key"]))
                if suggested:
                    st.session_state["workflow_formula_method_id"] = suggested.id
                navigate("formulae")
                st.rerun()
    c1, c2 = st.columns(2)
    if c1.button("Открыть рабочий процесс", key="import_to_workflow", width="stretch"):
        if dataset_ids:
            st.session_state["workflow_focus_dataset_id"] = int(dataset_ids[0])
        navigate("workflow")
        st.rerun()
    if c2.button("Построить график", key="import_to_plot", width="stretch"):
        st.session_state["workflow_plot_dataset_ids"] = [int(value) for value in dataset_ids]
        st.session_state.pop("quick_plot_datasets", None)
        navigate("plots")
        st.rerun()


def _sheet_settings(
    selected: list[str],
    default_header: int,
    default_mineral: str,
    prefix: str,
) -> tuple[dict[str, int], dict[str, str]]:
    header_rows: dict[str, int] = {}
    mineral_keys: dict[str, str] = {}
    mineral_keys_ordered = _import_mineral_keys()
    if len(selected) > 1:
        render_hint("У каждого выбранного листа можно задать собственный минерал и строку заголовков.")
    for index, sheet in enumerate(selected):
        label = sheet or "CSV"
        with st.expander(f"Настройки листа: {label}", expanded=index == 0 and len(selected) > 1):
            c1, c2 = st.columns(2)
            header_rows[sheet] = int(c1.number_input(
                "Строка заголовков", 1, 200, int(default_header), 1,
                key=f"{prefix}_header_{index}",
            ))
            mineral_keys[sheet] = c2.selectbox(
                "Минерал / режим", mineral_keys_ordered,
                index=mineral_keys_ordered.index(default_mineral),
                format_func=_import_mineral_label,
                key=f"{prefix}_mineral_{index}",
            )
    return header_rows, mineral_keys


def _manual_blocks(
    sheets: list[str],
    default_mineral: str,
    prefix: str,
    raw_preview: Callable[[str], pd.DataFrame],
) -> list[dict]:
    """Let a researcher mark several ordinary tables inside one messy worksheet."""
    if not sheets:
        return []
    st.subheader("Разметка таблиц на листе")
    render_hint(
        "Выберите лист и границы каждой таблицы. Номера строк берутся из Excel: строка заголовков входит в блок, "
        "последняя строка данных тоже входит. Примечания и другие таблицы между блоками не попадут в импорт."
    )
    sheet = st.selectbox("Лист для разметки", sheets, key=f"{prefix}_block_sheet")
    try:
        raw = raw_preview(sheet).head(120).copy()
        raw.insert(0, "Строка Excel", range(1, len(raw) + 1))
        st.dataframe(raw.fillna(""), width="stretch", hide_index=True, height=280)
        st.caption("Показаны первые 120 строк листа. Для таблицы ниже можно указать строки дальше этого предпросмотра.")
    except Exception as exc:
        st.error(f"Не удалось показать лист для разметки: {exc}")
        return []

    count = int(st.number_input("Таблиц на этом листе", 1, 12, 2, 1, key=f"{prefix}_block_count"))
    minerals = _import_mineral_keys()
    blocks: list[dict] = []
    for index in range(count):
        block_id = f"{prefix}_block_{index + 1}"
        with st.expander(f"Таблица {index + 1}", expanded=index == 0):
            c1, c2, c3 = st.columns(3)
            title = c1.text_input("Название", value=f"Таблица {index + 1}", key=f"{block_id}_title")
            header = int(c2.number_input("Строка заголовков", 1, 100_000, 1, 1, key=f"{block_id}_header"))
            last = int(c3.number_input("Последняя строка", 2, 100_000, 2, 1, key=f"{block_id}_last"))
            mineral = st.selectbox(
                "Минерал / режим", minerals, index=minerals.index(default_mineral),
                format_func=_import_mineral_label, key=f"{block_id}_mineral",
            )
            if last <= header:
                st.error("Последняя строка должна идти после строки заголовков.")
            blocks.append({
                "id": block_id, "sheet": sheet, "title": title,
                "header_row": header, "last_row": last, "mineral_key": mineral,
            })
    return blocks


def _block_mapping_and_preview(
    blocks: list[dict],
    *,
    inspector: Callable[[dict], ImportSchemaPreview],
    previewer: Callable[[dict, dict[str, str], dict[str, str]], pd.DataFrame],
    prefix: str,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], bool, int]:
    ids = [str(block["id"]) for block in blocks]
    lookup = {str(block["id"]): block for block in blocks}
    labels = {
        key: f"{item['sheet'] or 'CSV'} · {item['title']} ({item['header_row']}–{item['last_row']})"
        for key, item in lookup.items()
    }
    headers = {key: int(lookup[key]["header_row"]) for key in ids}
    semantic, measurement, ready = _schema_mapping(
        ids, lambda block_id, _header: inspector(lookup[block_id]), prefix, headers, labels,
    )
    row_count = 0
    if ready:
        ready, row_count = _render_normalized_previews(
            ids,
            lambda block_id: previewer(
                lookup[block_id], semantic.get(block_id, {}), measurement.get(block_id, {})
            ),
            labels,
        )
    return semantic, measurement, ready, row_count


def _raw_uploaded_rows(data: bytes, filename: str, sheet: str) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        return pd.read_excel(io.BytesIO(data), sheet_name=sheet or 0, header=None)
    try:
        return pd.read_csv(io.BytesIO(data), sep=None, engine="python", header=None)
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(data), sep=None, engine="python", header=None, encoding="cp1251")


def _schema_mapping(
    selected: list[str],
    inspector: Callable[[str, int], ImportSchemaPreview],
    prefix: str,
    header_rows: dict[str, int],
    labels: dict[str, str] | None = None,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, str]], bool]:
    semantic_maps: dict[str, dict[str, str]] = {}
    measurement_maps: dict[str, dict[str, str]] = {}
    ready = True
    if not selected:
        return semantic_maps, measurement_maps, ready

    st.subheader("Сопоставление колонок")
    render_hint(
        "Оксиды и элементы с единицами нормализуются автоматически. Неоднозначные роли и "
        "способ представления железа подтверждаются отдельно для каждого листа."
    )
    for sheet_index, sheet in enumerate(selected):
        label = (labels or {}).get(sheet, sheet or "CSV")
        try:
            preview = inspector(sheet, header_rows[sheet])
        except Exception as exc:
            st.error(f"{label}: не удалось прочитать заголовки — {exc}")
            ready = False
            continue

        with st.expander(f"Колонки: {label}", expanded=sheet_index == 0):
            if preview.adapter_name:
                st.success(f"Распознан формат: {preview.adapter_name}")
                if preview.adapter_note:
                    st.caption(preview.adapter_note)
            changed = [
                {"В Excel": original, "В PetroLab": normalized}
                for original, normalized in preview.source_headers if original != normalized
            ]
            if changed:
                st.dataframe(pd.DataFrame(changed), width="stretch", hide_index=True)
            if preview.measurement_notes:
                for note in preview.measurement_notes:
                    st.caption("• " + note)
            quality = st.columns(3)
            quality[0].metric("Строк", preview.row_count)
            quality[1].metric("Пустых ячеек", preview.empty_cells)
            quality[2].metric("<DL / <LOD", preview.detection_limit_cells)
            if preview.import_sections:
                st.caption("В этом EDS-протоколе найдены самостоятельные таблицы; порядок оксидов прочитан отдельно для каждой.")
                st.dataframe(
                    pd.DataFrame(preview.import_sections, columns=["Блок", "Анализов"]),
                    width="stretch", hide_index=True,
                )
            if preview.quality_counts:
                st.caption("Автоматический QC сохраняет все строки. Отмеченные точки не удаляются и будут заметны при построении графика.")
                st.dataframe(
                    pd.DataFrame(preview.quality_counts, columns=["QC уровень", "Строк"]),
                    width="stretch", hide_index=True,
                )
            chemical_rows = [
                {"В файле": source, "Будет храниться как": target, "Единица": unit, "Тип": "оксид"}
                for source, target, unit in preview.recognized_oxides
            ] + [
                {"В файле": source, "Будет храниться как": target, "Единица": unit, "Тип": "trace element"}
                for source, target, unit in preview.recognized_traces
            ]
            if chemical_rows:
                st.caption("Распознанная химия и единицы")
                st.dataframe(pd.DataFrame(chemical_rows), width="stretch", hide_index=True, height=min(280, 42 + 35 * len(chemical_rows)))
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


def _render_normalized_previews(
    selected: list[str],
    previewer: Callable[[str], pd.DataFrame],
    labels: dict[str, str] | None = None,
) -> tuple[bool, int]:
    """Show the actual future rows for every selected sheet before any write."""
    if not selected:
        return True, 0
    st.subheader("Предпросмотр перед сохранением")
    ready = True
    row_count = 0
    for index, sheet in enumerate(selected):
        label = (labels or {}).get(sheet, sheet or "CSV")
        try:
            dataframe = previewer(sheet)
            row_count += len(dataframe)
            with st.expander(f"{label} · будет создан новый набор", expanded=index == 0):
                st.caption(
                    f"После нормализации будет сохранено строк: {len(dataframe)}. "
                    "Добавление в уже существующий набор сейчас не выполняется: это защищает от случайного смешивания точек."
                )
                st.dataframe(dataframe.head(50), width="stretch", hide_index=True)
        except Exception as exc:
            st.error(f"{label}: не удалось построить предпросмотр — {exc}")
            ready = False
    return ready, row_count


def _render_import_readiness(*, ready: bool, table_count: int, row_count: int, manual: bool) -> None:
    """Make the point of no return legible before the import button."""
    if not table_count:
        return
    if ready:
        st.success(
            f"Готово к импорту: таблиц {table_count}; строк {row_count}. "
            "Будут созданы новые наборы PetroLab."
        )
    else:
        st.warning(
            "Импорт пока не готов: подтвердите все неоднозначные поля и исправьте отмеченные ошибки. "
            "Ничего ещё не записано."
        )
    if manual:
        st.caption("Ручная разметка сохранит границы каждой таблицы и исходные номера строк Excel.")
    st.caption("Исходный файл не изменяется этим действием. Для связанного XLSX/XLSM обратная синхронизация возможна только позже и с резервной копией.")


def _render_linked_import(project_id: int) -> None:
    st.subheader("Связать локальный файл")
    path_text = st.text_input("Полный путь к Excel/CSV", key="local_source_path")
    default_header = int(st.number_input(
        "Строка заголовков по умолчанию", 1, 200, 1, 1, key="local_header_row"
    ))
    if not path_text.strip():
        return
    try:
        source_path = Path(path_text).expanduser()
        sheets = list_linked_sheets(source_path)
    except Exception as exc:
        st.error(f"Не удалось открыть источник: {exc}")
        return

    suffix = source_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        st.info("XLSX/XLSM: доступна двусторонняя синхронизация с проверкой внешних изменений.")
    else:
        st.info("XLS/CSV: файл можно импортировать и перечитывать, но обратная запись в источник отключена.")

    mineral_options = _import_mineral_keys()
    default_mineral = st.selectbox(
        "Что находится в файле", mineral_options, index=0,
        format_func=_import_mineral_label, key="linked_mineral",
        help="Если в одном листе несколько фаз или минерал пока неизвестен, оставьте первый вариант — после импорта PetroLab откроет разбор фаз и выбросов.",
    )
    dataset_name = st.text_input("Название набора", value=source_path.stem, key="linked_dataset_name")
    target_project_id = _import_target(project_id, "linked_import_target")
    st.caption("При этом импорте будет создан новый набор. Добавление строк к уже существующему набору намеренно не выполняется без отдельного сопоставления точек.")
    mode = st.radio(
        "Как устроен файл",
        ["Одна готовая таблица на лист", "Разобрать вручную: несколько таблиц на одном листе"],
        horizontal=True, key="linked_import_mode",
    )
    blocks: list[dict] = []
    headers: dict[str, int] = {}
    minerals: dict[str, str] = {}
    if mode == "Разобрать вручную: несколько таблиц на одном листе":
        blocks = _manual_blocks(
            sheets, default_mineral, "linked",
            lambda sheet: _raw_uploaded_rows(source_path.read_bytes(), source_path.name, sheet),
        )
        semantic, measurement, ready, row_count = _block_mapping_and_preview(
            blocks,
            inspector=lambda block: inspect_linked_block(
                source_path, block["sheet"], block["header_row"], block["last_row"]
            ),
            previewer=lambda block, semantic_map, measurement_map: preview_linked_block(
                source_path, block["sheet"], block["header_row"], block["last_row"], block["mineral_key"],
                semantic_map, measurement_map,
            ),
            prefix="linked_block",
        )
        selected: list[str] = []
    else:
        selected = st.multiselect("Листы для импорта", sheets, default=sheets[:1], key="linked_sheets")
        headers, minerals = _sheet_settings(selected, default_header, default_mineral, "linked")
        semantic, measurement, ready = _schema_mapping(
            selected, lambda sheet, header: inspect_linked_sheet(source_path, sheet, header), "linked", headers,
        )
        row_count = 0
        if selected and ready:
            ready, row_count = _render_normalized_previews(
                selected,
                lambda sheet: preview_linked_source(
                    source_path, sheet, headers[sheet], minerals[sheet],
                    semantic.get(sheet, {}), measurement.get(sheet, {}),
                ),
            )

    table_count = len(blocks) if blocks else len(selected)
    _render_import_readiness(ready=ready, table_count=table_count, row_count=row_count, manual=bool(blocks))
    import_label = f"Связать и импортировать · {table_count} табл. · {row_count} строк"
    if st.button(import_label, type="primary", key="link_local", disabled=not (selected or blocks) or not ready):
        try:
            result = import_linked_sheets(
                project_id=target_project_id, path=source_path, sheet_names=selected,
                mineral_key=default_mineral, dataset_name=dataset_name, header_row=default_header,
                semantic_maps=semantic, measurement_maps=measurement,
                header_rows=headers, mineral_keys=minerals, blocks=blocks,
            )
            _continue_after_import(list(result.dataset_ids), project_id)
        except Exception as exc:
            st.error(f"Не удалось импортировать источник: {exc}")


def _render_uploaded_import(project_id: int) -> None:
    st.subheader("Импорт через браузер")
    uploaded = st.file_uploader("Excel или CSV", type=["xlsx", "xlsm", "xls", "csv"], key="upload_source")
    if uploaded is None:
        return
    data = uploaded.getvalue()
    default_header = int(st.number_input(
        "Строка заголовков по умолчанию", 1, 200, 1, 1, key="upload_header_row"
    ))
    try:
        sheets = list_uploaded_sheets(data, uploaded.name)
    except Exception as exc:
        st.error(f"Не удалось открыть загруженный файл: {exc}")
        return
    mineral_options = _import_mineral_keys()
    default_mineral = st.selectbox(
        "Что находится в файле", mineral_options, index=0,
        format_func=_import_mineral_label, key="upload_mineral",
        help="Если в одном листе несколько фаз или минерал пока неизвестен, оставьте первый вариант — после импорта PetroLab откроет разбор фаз и выбросов.",
    )
    dataset_name = st.text_input("Название набора", value=Path(uploaded.name).stem, key="upload_dataset_name")
    target_project_id = _import_target(project_id, "upload_import_target")
    st.caption("При этом импорте будет создан новый набор. Добавление строк к уже существующему набору намеренно не выполняется без отдельного сопоставления точек.")
    mode = st.radio(
        "Как устроен файл",
        ["Одна готовая таблица на лист", "Разобрать вручную: несколько таблиц на одном листе"],
        horizontal=True, key="upload_import_mode",
    )
    blocks: list[dict] = []
    headers: dict[str, int] = {}
    minerals: dict[str, str] = {}
    if mode == "Разобрать вручную: несколько таблиц на одном листе":
        blocks = _manual_blocks(sheets, default_mineral, "upload", lambda sheet: _raw_uploaded_rows(data, uploaded.name, sheet))
        semantic, measurement, ready, row_count = _block_mapping_and_preview(
            blocks,
            inspector=lambda block: inspect_uploaded_block(
                data, uploaded.name, block["sheet"], block["header_row"], block["last_row"]
            ),
            previewer=lambda block, semantic_map, measurement_map: preview_uploaded_block(
                data, uploaded.name, block["sheet"], block["header_row"], block["last_row"], block["mineral_key"],
                semantic_map, measurement_map,
            ),
            prefix="upload_block",
        )
        selected: list[str] = []
    else:
        selected = st.multiselect("Листы для импорта", sheets, default=sheets[:1], key="upload_sheets")
        headers, minerals = _sheet_settings(selected, default_header, default_mineral, "upload")
        semantic, measurement, ready = _schema_mapping(
            selected, lambda sheet, header: inspect_uploaded_sheet(data, uploaded.name, sheet, header), "upload", headers,
        )
        row_count = 0
        if selected and ready:
            ready, row_count = _render_normalized_previews(
                selected,
                lambda sheet: preview_uploaded_source(
                    data, uploaded.name, sheet, headers[sheet], minerals[sheet],
                    semantic.get(sheet, {}), measurement.get(sheet, {}),
                ),
            )
    table_count = len(blocks) if blocks else len(selected)
    _render_import_readiness(ready=ready, table_count=table_count, row_count=row_count, manual=bool(blocks))
    import_label = f"Импортировать рабочую копию · {table_count} табл. · {row_count} строк"
    if st.button(import_label, type="primary", key="upload_import", disabled=not (selected or blocks) or not ready):
        try:
            result = import_uploaded_sheets(
                project_id=target_project_id, file_bytes=data, filename=uploaded.name,
                sheet_names=selected, mineral_key=default_mineral, dataset_name=dataset_name,
                header_row=default_header, semantic_maps=semantic, measurement_maps=measurement,
                header_rows=headers, mineral_keys=minerals, blocks=blocks,
            )
            _continue_after_import(list(result.dataset_ids), project_id)
        except Exception as exc:
            st.error(f"Не удалось импортировать рабочую копию: {exc}")


def _managed_copy_status(dataset: dict) -> tuple[str, str]:
    path_text = str(dataset.get("source_path") or "")
    if not path_text:
        return "рабочая копия PetroLab", "Внутренняя копия без внешнего пути. Обратная запись в пользовательский оригинал недоступна."
    path = Path(path_text)
    if not path.exists():
        return "рабочая копия не найдена", str(path)
    stored_hash = str(dataset.get("source_sha256") or "")
    current_hash = sha256_file(path)
    if stored_hash and current_hash != stored_hash:
        return "рабочая копия изменена", str(path)
    return "рабочая копия PetroLab", str(path)


def _render_source_statuses(project_id: int) -> None:
    datasets = list_accessible_datasets(project_id)
    if not datasets:
        st.caption("Источников пока нет.")
        return
    for dataset in datasets:
        managed = str(dataset.get("source_kind") or "") == "managed_copy"
        try:
            schema = json.loads(str(dataset.get("column_map_json") or "{}"))
        except json.JSONDecodeError:
            schema = {}
        manual_block = bool((schema.get("__schema__") or {}).get("import_block"))
        if managed:
            status, detail = _managed_copy_status(dataset)
            origin_label = "внутренняя рабочая копия"
        elif manual_block:
            status = "ручной блок"
            detail = "Границы таблицы сохранены вместе с исходными строками Excel. Чтобы не сдвинуть точки после вставки заметки, обновление из файла отключено."
            origin_label = "зафиксированный фрагмент Excel"
        else:
            status, detail = source_status(dataset)
            origin_label = "связанный исходный файл" if str(dataset.get("source_kind") or "") == "linked" else "снимок без связи с файлом"
        with st.container(border=True):
            left, right = st.columns([4, 1])
            with left:
                st.markdown(f"**{dataset['name']}**")
                render_badges([
                    (status, "neutral" if managed else ("success" if status == "актуален" else "warning")),
                    (origin_label, "neutral"),
                ])
                st.caption(detail)
                if managed:
                    st.caption("Изменения базы не записываются в пользовательский оригинал. При обновлении будет прочитана эта рабочая копия.")
            with right:
                if not managed and not manual_block and status == "изменён вне ПетроЛаба":
                    if st.button("Перечитать исходный файл", key=f"refresh_source_{dataset['id']}", width="stretch"):
                        try:
                            result = refresh_dataset_from_source(int(dataset["id"]))
                            st.success(
                                f"Обновлено строк: {result.row_count}; сохранено ID: {result.reused_count}; "
                                f"новых: {result.new_count}; удалённых: {result.removed_count}."
                            )
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Обновление источника остановлено: {exc}")


def render_sources_dashboard_page() -> None:
    project = active_project()
    context = str(project["name"]) if project else "Проект не выбран"
    render_page_header(
        "Новые анализы",
        "Добавить файл → проверить листы → назначить сущности → preview и QC → сохранить → PetroLab предложит следующий научный шаг.",
        eyebrow="Данные",
        context=context,
    )
    if project is None:
        st.info("Сначала создайте проект.")
        return
    render_work_context(
        area=f"проект «{project['name']}» · импорт новых данных",
        note="файл → разметка → проверка → новый набор PetroLab",
    )
    _render_import_continue(int(project["id"]))
    render_badges([
        ("1 · Файл", "accent"), ("2 · Листы", "neutral"),
        ("3 · Сопоставление", "neutral"), ("4 · Проверка", "neutral"),
        ("5 · Импорт", "neutral"),
    ])
    linked, uploaded, sources = st.tabs([
        "Связать файл на компьютере",
        "Загрузить рабочую копию",
        "Источники и рабочие копии",
    ])
    with linked:
        render_hint("PetroLab запомнит путь. Для XLSX/XLSM возможна безопасная обратная синхронизация.")
        _render_linked_import(int(project["id"]))
    with uploaded:
        render_hint("PetroLab сохранит внутреннюю рабочую копию файла. Она не является sync-target пользовательского оригинала.")
        _render_uploaded_import(int(project["id"]))
    with sources:
        _render_source_statuses(int(project["id"]))

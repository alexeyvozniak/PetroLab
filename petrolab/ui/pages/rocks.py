from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import streamlit as st

from petrolab.db import list_datasets
from petrolab.repositories.rock_repository import (
    create_rock,
    get_composition,
    get_isotopes,
    get_rock,
    list_mineral_links,
    list_rocks,
    replace_isotopes,
    set_mineral_links as _set_mineral_links,
    update_rock,
    upsert_composition_values,
)
from petrolab.services.rock_image_service import (
    delete_rock_image as _delete_rock_image,
    list_rock_images,
    save_rock_image,
)
from petrolab.services.rock_service import (
    composition_dict,
    delete_rock_with_assets,
    import_rocks_wide,
    whole_rock_mg_number,
)
from petrolab.ui.destructive_actions import confirm_then, pending_key, render_pending
from petrolab.ui.layout import render_page_header
from petrolab.ui.project_context import active_project_id
from petrolab.ui.rock_plots import render_rock_plots


META_ROLE_LABELS = {
    "massif": "Массив / комплекс",
    "locality": "Местоположение",
    "lithology": "Название породы / литология",
    "age_ma": "Возраст, млн лет",
    "age_uncertainty_ma": "Ошибка возраста, млн лет",
}
CONFLICT_OPTIONS = {
    "Обновить существующую породу": "update",
    "Пропустить существующую породу": "skip",
    "Считать совпадение ошибкой": "error",
}


def _rock_label(rock: dict) -> str:
    extra = " · ".join(
        value
        for value in [str(rock.get("massif", "")).strip(), str(rock.get("lithology", "")).strip()]
        if value
    )
    return f"{rock['name']}" + (f" · {extra}" if extra else "")


def _read_uploaded_rock_table(uploaded) -> pd.DataFrame:
    suffix = Path(uploaded.name).suffix.lower()
    content = uploaded.getvalue()
    if suffix in {".xlsx", ".xls"}:
        workbook = pd.ExcelFile(io.BytesIO(content))
        sheet = st.selectbox("Лист", workbook.sheet_names, key="rock_bulk_sheet")
        return pd.read_excel(io.BytesIO(content), sheet_name=sheet)

    s1, s2 = st.columns(2)
    separator_name = s1.selectbox(
        "Разделитель",
        ["Определить автоматически", "Запятая", "Точка с запятой", "Табуляция"],
        key="rock_bulk_separator",
    )
    decimal_name = s2.selectbox("Десятичный знак", ["Точка", "Запятая"], key="rock_bulk_decimal")
    separators = {
        "Определить автоматически": None,
        "Запятая": ",",
        "Точка с запятой": ";",
        "Табуляция": "\t",
    }
    separator = separators[separator_name]
    return pd.read_csv(
        io.BytesIO(content),
        sep=separator,
        engine="python" if separator is None else "c",
        decimal="." if decimal_name == "Точка" else ",",
    )


def _render_bulk_import(project_id: int) -> None:
    with st.expander("Импортировать таблицу валовых составов", expanded=False):
        uploaded = st.file_uploader(
            "Excel/CSV с породами",
            type=["xlsx", "xls", "csv", "tsv"],
            key="rock_bulk_upload",
        )
        if uploaded is None:
            return
        try:
            dataframe = _read_uploaded_rock_table(uploaded).dropna(how="all")
        except Exception as exc:
            st.error(f"Не удалось прочитать таблицу: {exc}")
            return
        if dataframe.empty:
            st.warning("Таблица пуста.")
            return

        st.dataframe(dataframe.head(20), width="stretch", hide_index=True)
        columns = [str(column) for column in dataframe.columns]
        name_column = st.selectbox("Колонка с названием образца/породы", columns, key="rock_bulk_name")
        metadata_columns: dict[str, str] = {}
        with st.expander("Сопоставить паспортные поля", expanded=False):
            for role, label in META_ROLE_LABELS.items():
                choice = st.selectbox(label, ["—"] + columns, key=f"rock_meta_{role}")
                if choice != "—":
                    metadata_columns[role] = choice
        c1, c2 = st.columns(2)
        method = c1.text_input("Метод химии", placeholder="XRF + ICP-MS", key="rock_bulk_method")
        laboratory = c2.text_input("Лаборатория", key="rock_bulk_lab")
        conflict_label = st.selectbox(
            "Если название уже есть в проекте",
            list(CONFLICT_OPTIONS),
            key="rock_bulk_conflict",
        )
        st.caption(
            "Перед записью ПетроЛаб проверяет повторяющиеся названия внутри файла. "
            "Две строки с одинаковым названием в одной импортируемой таблице считаются неоднозначными."
        )
        if st.button("Импортировать породы", type="primary", key="rock_bulk_import"):
            try:
                result = import_rocks_wide(
                    dataframe,
                    project_id=project_id,
                    name_column=name_column,
                    metadata_columns=metadata_columns,
                    chemistry_method=method,
                    laboratory=laboratory,
                    source=uploaded.name,
                    on_conflict=CONFLICT_OPTIONS[conflict_label],
                )
            except Exception as exc:
                st.error(f"Импорт не выполнен: {exc}")
                return
            st.success(
                f"Создано: {len(result.created_ids)} · обновлено: {len(result.updated_ids)} · "
                f"пропущено: {len(result.skipped_names)}"
            )
            if result.warnings:
                st.warning("\n".join(result.warnings[:30]))
            st.rerun()


def _render_passport(rock: dict) -> None:
    rock_id = int(rock["id"])
    with st.form(f"rock_passport_{rock_id}"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Название / образец", value=str(rock.get("name", "")))
        lithology = c2.text_input("Порода / литология", value=str(rock.get("lithology", "")))
        c3, c4 = st.columns(2)
        massif = c3.text_input("Массив / комплекс", value=str(rock.get("massif", "")))
        locality = c4.text_input("Местоположение", value=str(rock.get("locality", "")))
        description = st.text_area("Описание породы", value=str(rock.get("description", "")), height=110)
        a1, a2, a3 = st.columns(3)
        age_ma = a1.number_input(
            "Возраст, млн лет",
            value=float(rock["age_ma"]) if rock.get("age_ma") is not None else None,
            placeholder="не указан",
        )
        age_err = a2.number_input(
            "±, млн лет",
            value=float(rock["age_uncertainty_ma"]) if rock.get("age_uncertainty_ma") is not None else None,
            placeholder="не указана",
        )
        age_method = a3.text_input(
            "Метод возраста",
            value=str(rock.get("age_method", "")),
            placeholder="U–Pb zircon, Rb–Sr...",
        )
        m1, m2 = st.columns(2)
        chemistry_method = m1.text_area(
            "Методика химии",
            value=str(rock.get("chemistry_method", "")),
            height=90,
        )
        isotope_method = m2.text_area(
            "Методика изотопии",
            value=str(rock.get("isotope_method", "")),
            height=90,
        )
        laboratory = st.text_input(
            "Лаборатория / где выполнялись анализы",
            value=str(rock.get("laboratory", "")),
        )
        notes = st.text_area("Заметки", value=str(rock.get("notes", "")), height=90)
        if st.form_submit_button("Сохранить паспорт", type="primary"):
            try:
                update_rock(
                    rock_id,
                    name=name,
                    lithology=lithology,
                    massif=massif,
                    locality=locality,
                    description=description,
                    age_ma=age_ma,
                    age_uncertainty_ma=age_err,
                    age_method=age_method,
                    chemistry_method=chemistry_method,
                    isotope_method=isotope_method,
                    laboratory=laboratory,
                    notes=notes,
                )
            except Exception as exc:
                st.error(f"Не удалось сохранить паспорт: {exc}")
            else:
                st.success("Паспорт сохранён.")
                st.rerun()


def _render_composition(rock: dict) -> None:
    rock_id = int(rock["id"])
    composition = get_composition(rock_id)
    if composition.empty:
        composition = pd.DataFrame(columns=["analyte", "value", "unit", "method", "source"])
    else:
        composition = composition[["analyte", "value", "unit", "method", "source"]]
    edited = st.data_editor(
        composition,
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"rock_comp_editor_{rock_id}",
        column_config={
            "analyte": st.column_config.TextColumn("Компонент", required=True),
            "value": st.column_config.NumberColumn("Значение"),
            "unit": st.column_config.TextColumn("Единица"),
            "method": st.column_config.TextColumn("Метод"),
            "source": st.column_config.TextColumn("Источник / файл"),
        },
    )
    if st.button("Сохранить химический состав", type="primary", key=f"rock_comp_save_{rock_id}"):
        try:
            upsert_composition_values(rock_id, edited.to_dict("records"))
            st.success("Химический состав сохранён.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось сохранить состав: {exc}")
    mgnum = whole_rock_mg_number(composition_dict(rock_id))
    st.metric("Whole-rock Mg# (Fe²⁺ proxy)", "—" if pd.isna(mgnum) else f"{mgnum:.3f}")
    st.caption(
        "Если в породе задано total Fe, Mg# здесь является прозрачным proxy. "
        "Для redox-aware screening Fe³⁺-доля задаётся отдельно в mineral–rock модуле."
    )


def _render_isotopes(rock: dict) -> None:
    rock_id = int(rock["id"])
    isotopes = get_isotopes(rock_id)
    columns = [
        "system", "ratio_name", "analysis_label", "value", "uncertainty", "initial_value",
        "age_ma_used", "method", "laboratory", "source", "notes",
    ]
    if isotopes.empty:
        isotopes = pd.DataFrame(columns=columns)
    st.caption(
        "Одинаковое изотопное отношение можно сохранить несколько раз. Для повторных определений "
        "задайте метку aliquot/определения; если оставить её пустой, в wide-view будут использованы rep 1, rep 2 и т. д."
    )
    edited = st.data_editor(
        isotopes[columns],
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"rock_iso_editor_{rock_id}",
        column_config={
            "system": st.column_config.TextColumn("Система"),
            "ratio_name": st.column_config.TextColumn("Отношение", required=True),
            "analysis_label": st.column_config.TextColumn("Определение / aliquot"),
            "value": st.column_config.NumberColumn("Значение", format="%.8g"),
            "uncertainty": st.column_config.NumberColumn("Неопределённость", format="%.6g"),
            "initial_value": st.column_config.NumberColumn("Начальное значение", format="%.8g"),
            "age_ma_used": st.column_config.NumberColumn("Возраст, млн лет"),
            "method": st.column_config.TextColumn("Метод"),
            "laboratory": st.column_config.TextColumn("Лаборатория"),
            "source": st.column_config.TextColumn("Источник / файл"),
            "notes": st.column_config.TextColumn("Заметки"),
        },
    )
    if st.button("Сохранить изотопию", type="primary", key=f"rock_iso_save_{rock_id}"):
        try:
            replace_isotopes(rock_id, edited)
            st.success("Изотопные данные сохранены.")
            st.rerun()
        except Exception as exc:
            st.error(f"Не удалось сохранить изотопию: {exc}")


def _render_links_and_images(rock: dict) -> None:
    rock_id = int(rock["id"])
    datasets = list_datasets(int(rock["project_id"]))
    label_to_id = {
        f"{dataset['name']} · {dataset['mineral_key']} · {dataset['source_filename']}": int(dataset["id"])
        for dataset in datasets
    }
    current = {int(value) for value in list_mineral_links(rock_id)}
    selected_labels = st.multiselect(
        "Минералогические наборы из этой породы",
        list(label_to_id),
        default=[label for label, dataset_id in label_to_id.items() if dataset_id in current],
        key=f"rock_links_{rock_id}",
    )
    new_ids = tuple(sorted(label_to_id[label] for label in selected_labels))
    removed = current - set(new_ids)
    link_target = (rock_id, *new_ids)
    if removed and st.session_state.get(pending_key("rock_links")) == link_target:
        render_pending(
            "rock_links",
            f"Будет удалено связей минерал–порода: {len(removed)}. Нажмите «Сохранить связи минерал–порода» ещё раз или отмените действие.",
        )
    if st.button("Сохранить связи минерал–порода", key=f"rock_links_save_{rock_id}"):
        if removed:
            if confirm_then("rock_links", link_target, lambda: _set_mineral_links(rock_id, new_ids)):
                st.success("Связи сохранены.")
                st.rerun()
        else:
            _set_mineral_links(rock_id, new_ids)
            st.success("Связи сохранены.")

    st.divider()
    uploads = st.file_uploader(
        "Общие фотографии породы",
        type=["png", "jpg", "jpeg", "tif", "tiff", "webp"],
        accept_multiple_files=True,
        key=f"rock_images_upload_{rock_id}",
    )
    if uploads and st.button("Сохранить фотографии", key=f"rock_images_save_{rock_id}"):
        saved = 0
        for upload in uploads:
            try:
                save_rock_image(rock_id, upload.name, upload.getvalue())
                saved += 1
            except Exception as exc:
                st.error(f"{upload.name}: {exc}")
        if saved:
            st.success(f"Сохранено изображений: {saved}")
            st.rerun()

    images = list_rock_images(rock_id)
    if not images:
        return
    columns = st.columns(min(3, len(images)))
    for index, image in enumerate(images):
        image_id = int(image["id"])
        path = Path(str(image["stored_path"]))
        with columns[index % len(columns)]:
            if path.exists():
                st.image(
                    str(path),
                    caption=image["title"] or image["original_filename"],
                    width="stretch",
                )
            if st.session_state.get(pending_key("rock_image")) == image_id:
                render_pending(
                    "rock_image",
                    "Фотография породы будет удалена с диска и из базы. Нажмите «Удалить» ещё раз или отмените действие.",
                )
            if st.button("Удалить", key=f"rock_image_delete_{image_id}"):
                if confirm_then("rock_image", image_id, lambda: _delete_rock_image(image_id)):
                    st.rerun()


def render_rocks_page() -> None:
    render_page_header(
        "Породы",
        "Валовые составы, изотопия, возраст, методика, фотографии и связи с минералогическими наборами.",
        eyebrow="Материалы",
    )
    project_id = active_project_id()
    if project_id is None:
        st.info("Сначала создайте проект.")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        with st.expander("Новая порода", expanded=False):
            name = st.text_input("Название", key="rock_new_name")
            if st.button("Создать", type="primary", key="rock_new_create") and name.strip():
                try:
                    create_rock(project_id, name.strip())
                    st.success("Порода создана.")
                    st.rerun()
                except Exception as exc:
                    st.error(str(exc))
    with c2:
        _render_bulk_import(project_id)

    rocks = list_rocks(project_id)
    if not rocks:
        st.info("Создайте породу вручную или импортируйте таблицу валовых составов.")
        return
    rock_map = {_rock_label(rock): rock for rock in rocks}
    selected_label = st.selectbox("Открыть породу", list(rock_map), key="rock_select")
    selected = get_rock(int(rock_map[selected_label]["id"]))
    if selected is None:
        return

    tabs = st.tabs([
        "Паспорт", "Валовый состав", "Изотопия", "Минералы и фото", "Графики / mineral–rock",
    ])
    with tabs[0]:
        _render_passport(selected)
        with st.expander("Опасная зона", expanded=False):
            confirm = st.checkbox(
                "Я понимаю, что порода и её локальные фотографии будут удалены",
                key=f"rock_delete_confirm_{selected['id']}",
            )
            if st.button(
                "Удалить породу",
                disabled=not confirm,
                key=f"rock_delete_{selected['id']}",
            ):
                try:
                    delete_rock_with_assets(int(selected["id"]))
                except Exception as exc:
                    st.error(f"Не удалось удалить породу: {exc}")
                else:
                    st.rerun()
    with tabs[1]:
        _render_composition(selected)
    with tabs[2]:
        _render_isotopes(selected)
    with tabs[3]:
        _render_links_and_images(selected)
    with tabs[4]:
        render_rock_plots(project_id, selected)

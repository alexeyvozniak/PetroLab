from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st

from petrolab.db import list_datasets
from petrolab.derived import load_unified_with_derived
from petrolab.extended_plotting import (
    NORMALIZATION_REFERENCES,
    REE_ORDER,
    SPIDER_ORDER,
    available_elements,
    build_pattern_figure,
    prepare_pattern,
)
from petrolab.repositories.rock_repository import (
    composition_wide,
    create_rock,
    delete_rock,
    get_composition,
    get_isotopes,
    get_rock,
    isotope_wide,
    list_mineral_links,
    list_rocks,
    replace_isotopes,
    set_mineral_links,
    update_rock,
    upsert_composition_values,
)
from petrolab.rock_plotting import build_rhodes_figure, build_rock_scatter, build_tas_figure, figure_bytes
from petrolab.services.rock_image_service import delete_rock_image, list_rock_images, save_rock_image
from petrolab.services.rock_service import (
    composition_dict,
    import_rocks_wide,
    measured_olivine_kd,
    whole_rock_mg_number,
)
from petrolab.ui.components import render_project_selector


META_ROLE_LABELS = {
    "massif": "Массив / комплекс",
    "locality": "Местоположение",
    "lithology": "Название породы / литология",
    "age_ma": "Возраст, млн лет",
    "age_uncertainty_ma": "Ошибка возраста, млн лет",
}


def _rock_label(rock: dict) -> str:
    extra = " · ".join(value for value in [str(rock.get("massif", "")).strip(), str(rock.get("lithology", "")).strip()] if value)
    return f"{rock['name']}" + (f" · {extra}" if extra else "")


def _render_bulk_import(project_id: int) -> None:
    with st.expander("Импортировать таблицу валовых составов", expanded=False):
        uploaded = st.file_uploader("Excel/CSV с породами", type=["xlsx", "xls", "csv", "tsv"], key="rock_bulk_upload")
        if uploaded is None:
            return
        suffix = Path(uploaded.name).suffix.lower()
        if suffix in {".xlsx", ".xls"}:
            workbook = pd.ExcelFile(uploaded)
            sheet = st.selectbox("Лист", workbook.sheet_names, key="rock_bulk_sheet")
            dataframe = pd.read_excel(workbook, sheet_name=sheet)
        else:
            separator = "\t" if suffix == ".tsv" else ","
            dataframe = pd.read_csv(uploaded, sep=separator)
        dataframe = dataframe.dropna(how="all")
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
                )
            except Exception as exc:
                st.error(f"Импорт не выполнен: {exc}")
                return
            st.success(f"Добавлено пород: {len(result.created_ids)}")
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
        age_ma = a1.number_input("Возраст, млн лет", value=float(rock["age_ma"]) if rock.get("age_ma") is not None else None, placeholder="не указан")
        age_err = a2.number_input("±, млн лет", value=float(rock["age_uncertainty_ma"]) if rock.get("age_uncertainty_ma") is not None else None, placeholder="не указана")
        age_method = a3.text_input("Метод возраста", value=str(rock.get("age_method", "")), placeholder="U–Pb zircon, Rb–Sr...")
        m1, m2 = st.columns(2)
        chemistry_method = m1.text_area("Методика химии", value=str(rock.get("chemistry_method", "")), height=90)
        isotope_method = m2.text_area("Методика изотопии", value=str(rock.get("isotope_method", "")), height=90)
        laboratory = st.text_input("Лаборатория / где выполнялись анализы", value=str(rock.get("laboratory", "")))
        notes = st.text_area("Заметки", value=str(rock.get("notes", "")), height=90)
        if st.form_submit_button("Сохранить паспорт", type="primary"):
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
        except Exception as exc:
            st.error(f"Не удалось сохранить состав: {exc}")
    mgnum = whole_rock_mg_number(composition_dict(rock_id))
    st.metric("Whole-rock Mg# (Fe²⁺ proxy)", "—" if pd.isna(mgnum) else f"{mgnum:.3f}")
    st.caption("Если в породе задано total Fe, Mg# здесь является прозрачным proxy. Для redox-aware расчёта задайте Fe³⁺-долю в mineral–rock модуле.")


def _render_isotopes(rock: dict) -> None:
    rock_id = int(rock["id"])
    isotopes = get_isotopes(rock_id)
    columns = ["system", "ratio_name", "value", "uncertainty", "initial_value", "age_ma_used", "method", "laboratory", "notes"]
    if isotopes.empty:
        isotopes = pd.DataFrame(columns=columns)
    edited = st.data_editor(
        isotopes[columns],
        num_rows="dynamic",
        width="stretch",
        hide_index=True,
        key=f"rock_iso_editor_{rock_id}",
    )
    if st.button("Сохранить изотопию", type="primary", key=f"rock_iso_save_{rock_id}"):
        try:
            replace_isotopes(rock_id, edited)
            st.success("Изотопные данные сохранены.")
        except Exception as exc:
            st.error(f"Не удалось сохранить изотопию: {exc}")


def _render_links_and_images(rock: dict) -> None:
    rock_id = int(rock["id"])
    datasets = list_datasets(int(rock["project_id"]))
    label_to_id = {
        f"{dataset['name']} · {dataset['mineral_key']} · {dataset['source_filename']}": int(dataset["id"])
        for dataset in datasets
    }
    current = set(list_mineral_links(rock_id))
    selected_labels = st.multiselect(
        "Минералогические наборы из этой породы",
        list(label_to_id),
        default=[label for label, dataset_id in label_to_id.items() if dataset_id in current],
        key=f"rock_links_{rock_id}",
    )
    if st.button("Сохранить связи минерал–порода", key=f"rock_links_save_{rock_id}"):
        set_mineral_links(rock_id, [label_to_id[label] for label in selected_labels])
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
    if images:
        columns = st.columns(min(3, len(images)))
        for index, image in enumerate(images):
            path = Path(str(image["stored_path"]))
            with columns[index % len(columns)]:
                if path.exists():
                    st.image(str(path), caption=image["title"] or image["original_filename"], width="stretch")
                if st.button("Удалить", key=f"rock_image_delete_{image['id']}"):
                    delete_rock_image(int(image["id"]))
                    st.rerun()


def _render_rock_plots(project_id: int, selected_rock: dict) -> None:
    wide = composition_wide(project_id)
    if wide.empty:
        st.info("Сначала внесите валовый химический состав.")
        return
    tab_tas, tab_harker, tab_pattern, tab_iso, tab_rhodes = st.tabs(["TAS", "Harker / бинарные", "REE / Spider", "Изотопы", "Mineral–rock / Rhodes"])

    with tab_tas:
        required = {"SiO2", "Na2O", "K2O"}
        if required.issubset(wide.columns):
            fig = build_tas_figure(wide, group_column="Massif" if "Massif" in wide else None)
            st.pyplot(fig, width="stretch")
            st.download_button("TAS PNG", figure_bytes(fig, "png", 600), file_name="TAS.png", mime="image/png", key="rock_tas_png")
            plt.close(fig)
        else:
            st.info("Для TAS нужны SiO2, Na2O и K2O.")

    with tab_harker:
        numeric = [column for column in wide.columns if pd.to_numeric(wide[column], errors="coerce").notna().sum() >= 2 and not str(column).startswith("_")]
        if numeric:
            x_default = "SiO2" if "SiO2" in numeric else numeric[0]
            c1, c2 = st.columns(2)
            x = c1.selectbox("X", numeric, index=numeric.index(x_default), key="rock_harker_x")
            y_choices = [column for column in numeric if column != x]
            if y_choices:
                y = c2.selectbox("Y", y_choices, key="rock_harker_y")
                fig = build_rock_scatter(wide, x, y, group_column="Massif" if "Massif" in wide else None, title=f"{y} vs {x}")
                st.pyplot(fig, width="stretch")
                st.download_button("PNG", figure_bytes(fig, "png", 600), file_name=f"{y}_vs_{x}.png", mime="image/png", key="rock_harker_png")
                plt.close(fig)

    with tab_pattern:
        mode = st.segmented_control("Тип", ["REE", "Spider"], default="REE", key="rock_pattern_mode")
        order = REE_ORDER if mode == "REE" else SPIDER_ORDER
        available = available_elements(wide, order)
        if len(available) >= 2:
            elements = st.multiselect("Элементы", list(order), default=available, key="rock_pattern_elements")
            ref_name = st.selectbox("Нормировка", list(NORMALIZATION_REFERENCES), index=1 if mode == "REE" else 2, key="rock_pattern_ref")
            pattern = prepare_pattern(wide, elements, NORMALIZATION_REFERENCES[ref_name])
            labels = wide["Rock"] if "Rock" in wide else None
            groups = wide["Massif"] if "Massif" in wide else None
            fig = build_pattern_figure(pattern, labels=labels, group=groups, title=f"Whole-rock {mode}", ylabel="Sample / reference" if ref_name != "Без нормировки" else "Concentration")
            st.pyplot(fig, width="stretch")
            st.download_button("PNG", figure_bytes(fig, "png", 600), file_name=f"whole_rock_{mode}.png", mime="image/png", key="rock_pattern_png")
            plt.close(fig)
        else:
            st.info("Недостаточно trace-element данных.")

    with tab_iso:
        isotopes = isotope_wide(project_id)
        numeric = [column for column in isotopes.columns if pd.to_numeric(isotopes[column], errors="coerce").notna().sum() >= 2 and not str(column).startswith("_")]
        if len(numeric) >= 2:
            x = st.selectbox("Изотопная X", numeric, key="rock_iso_x")
            y = st.selectbox("Изотопная Y", [column for column in numeric if column != x], key="rock_iso_y")
            fig = build_rock_scatter(isotopes, x, y, title=f"{y} vs {x}")
            st.pyplot(fig, width="stretch")
            plt.close(fig)
        else:
            st.info("Добавьте как минимум две числовые изотопные величины у нескольких пород.")

    with tab_rhodes:
        links = list_mineral_links(int(selected_rock["id"]))
        if not links:
            st.info("Свяжите породу с минералогическим dataset.")
            return
        minerals = load_unified_with_derived(int(selected_rock["project_id"]), links)
        olivine = minerals[minerals["Минерал"].astype(str).eq("olivine")].copy() if "Минерал" in minerals else pd.DataFrame()
        if olivine.empty or "Fo" not in olivine.columns:
            st.info("Для Rhodes нужен связанный набор оливинов с сохранённым Fo.")
            return
        comp = composition_dict(int(selected_rock["id"]))
        fe3 = st.slider("Доля Fe³⁺ в total Fe породы для Mg# proxy", 0.0, 0.5, 0.0, 0.01, key="rock_rhodes_fe3")
        mgnum = whole_rock_mg_number(comp, fe3_fraction=fe3)
        if pd.isna(mgnum):
            st.warning("Невозможно рассчитать whole-rock Mg#: нужны MgO и FeO/FeOt/Fe2O3t.")
            return
        rock_row = pd.DataFrame([{"Rock": selected_rock["name"], "Mg#_rock": mgnum}])
        fig = build_rhodes_figure(rock_row, olivine)
        st.pyplot(fig, width="stretch")
        kd = measured_olivine_kd(olivine["Fo"], mgnum)
        view_columns = [column for column in ["Sample", "Grain", "Point", "Fo"] if column in olivine.columns]
        kd_table = olivine[view_columns].copy()
        kd_table["Kd_FeMg_ol-rock_proxy"] = kd.to_numpy()
        st.dataframe(kd_table, width="stretch", hide_index=True, height=320)
        st.caption("Это equilibrium-screening proxy. Whole-rock состав не всегда равен составу расплава; интерпретация особенно осторожна для кумулятов, ксенокристов и контаминированных лампрофиров/кимберлитов.")
        plt.close(fig)


def render_rocks_page() -> None:
    st.title("Породы")
    st.write(
        "Отдельная база валовых составов, изотопии, возраста, методики и фотографий. "
        "Породы связываются с минералогическими dataset'ами без копирования анализов."
    )
    project = render_project_selector("rocks_project")
    if project is None:
        return
    project_id = int(project["id"])

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

    tabs = st.tabs(["Паспорт", "Валовый состав", "Изотопия", "Минералы и фото", "Графики / mineral–rock"])
    with tabs[0]:
        _render_passport(selected)
        with st.expander("Опасная зона", expanded=False):
            if st.button("Удалить породу", key=f"rock_delete_{selected['id']}"):
                delete_rock(int(selected["id"]))
                st.rerun()
    with tabs[1]:
        _render_composition(selected)
    with tabs[2]:
        _render_isotopes(selected)
    with tabs[3]:
        _render_links_and_images(selected)
    with tabs[4]:
        _render_rock_plots(project_id, selected)

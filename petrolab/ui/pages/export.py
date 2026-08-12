from __future__ import annotations

import io
import json

import pandas as pd
import streamlit as st

from petrolab.dataframe_utils import dataset_label
from petrolab.db import list_datasets, list_plot_recipes, list_style_profiles
from petrolab.derived import formula_provenance_rows, load_unified_with_derived
from petrolab.services.image_service import image_export_records


def render_export_page() -> None:
    st.title("Экспорт общей базы")
    datasets = list_datasets()
    if not datasets:
        st.info("Пока нечего экспортировать.")
        return

    labels = {dataset_label(dataset): int(dataset["id"]) for dataset in datasets}
    selected = st.multiselect("Наборы", list(labels), default=list(labels), key="export_datasets")
    dataset_ids = [labels[label] for label in selected]
    if not dataset_ids:
        return

    dataframe = load_unified_with_derived(dataset_ids=dataset_ids)
    st.dataframe(dataframe.head(80), width="stretch", hide_index=True)
    export_dataframe = dataframe[[column for column in dataframe.columns if not str(column).startswith("_")]].copy()

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_dataframe.to_excel(writer, index=False, sheet_name="Все анализы")
        pd.DataFrame(image_export_records()).to_excel(writer, index=False, sheet_name="Изображения")

        provenance = formula_provenance_rows(dataset_ids)
        if provenance:
            pd.DataFrame(provenance).to_excel(writer, index=False, sheet_name="Методы пересчёта")

        recipes = list_plot_recipes()
        if recipes:
            pd.DataFrame(
                [
                    {
                        "id": record["id"],
                        "project_id": record["project_id"],
                        "name": record["name"],
                        "created_at": record["created_at"],
                        "updated_at": record["updated_at"],
                        "config": json.dumps(record["config"], ensure_ascii=False),
                    }
                    for record in recipes
                ]
            ).to_excel(writer, index=False, sheet_name="Рецепты графиков")

        profiles = list_style_profiles()
        if profiles:
            pd.DataFrame(
                [
                    {
                        "id": record["id"],
                        "project_id": record["project_id"],
                        "name": record["name"],
                        "grouping_column": record["grouping_column"],
                        "created_at": record["created_at"],
                        "updated_at": record["updated_at"],
                        "styles": json.dumps(record["styles"], ensure_ascii=False),
                    }
                    for record in profiles
                ]
            ).to_excel(writer, index=False, sheet_name="Профили стилей")

    st.download_button(
        "Единый Excel",
        buffer.getvalue(),
        file_name="PetroLab_единая_база.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )

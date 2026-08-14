from __future__ import annotations
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.ui.project_context import active_project_id
from petrolab.ui.layout import render_hint, render_page_header
from petrolab.partition_seed_models import seed_initial_alkaline_models
from petrolab.partition_import import import_partition_table, read_partition_upload

_META={"_analysis_id","_dataset_id","_project_id","_row_index","_source_row"}
def render_distribution_page() -> None:
    render_page_header("Распределение элементов", "Первый безопасный режим: наблюдаемые отношения двух конкретных анализов. Это не литературный равновесный D и не Kd обмена.", eyebrow="Исследование")
    project_id=active_project_id()
    if project_id is None: st.info("Сначала выберите проект."); return
    with st.expander("Библиотека D: щелочные системы", expanded=False):
        st.caption("Добавляет две экспериментальные модели LaTourrette et al. (1995): Phl–basanite melt и Amp–basanite melt. Они не заменяют ваши собственные D и не применяются автоматически.")
        if st.button("Добавить проверенные basanite-модели"):
            made=seed_initial_alkaline_models()
            st.success("Добавлено моделей: "+str(len(made)) if made else "Эти модели уже есть в библиотеке.")
    with st.expander("Импорт полной литературной таблицы D", expanded=False):
        upload=st.file_uploader("GERM / собственная таблица (CSV, TSV или Excel)", type=["csv","tsv","txt","xlsx","xls"], key="partition_table_upload")
        st.caption("Поддерживается текущий экспорт GERM KdD: Rock Types, Minerals, Kd, Kd Sigma, Kd Low, Kd High, Definition и Type. Импортируются любые элементы, включая главные; интервал не превращается в среднее. Значения в GERM заданы по элементам, не по оксидам.")
        if upload is not None and st.button("Импортировать таблицу D"):
            try:
                raw=upload.getvalue()
                df=read_partition_upload(raw, upload.name)
                made=import_partition_table(df)
                st.success(f"Создано литературных моделей: {len(made)}")
            except Exception as exc: st.error(str(exc))
    datasets=list_accessible_datasets(project_id)
    if not datasets: st.info("В проекте пока нет анализов."); return
    labels={f"{d['name']} · {d['mineral_key']}":d for d in datasets}
    left_label=st.selectbox("Числитель: набор",list(labels),key="ratio_left")
    right_label=st.selectbox("Знаменатель: набор",list(labels),index=list(labels).index(left_label),key="ratio_right")
    left,right=load_dataset_dataframe(int(labels[left_label]['id'])),load_dataset_dataframe(int(labels[right_label]['id']))
    if left.empty or right.empty: st.info("В выбранном наборе нет анализов."); return
    a=st.selectbox("Точка в числителе",left["_analysis_id"].astype(str).tolist())
    b=st.selectbox("Точка в знаменателе",right["_analysis_id"].astype(str).tolist())
    row_a=left.loc[left["_analysis_id"].astype(str)==a].iloc[0]; row_b=right.loc[right["_analysis_id"].astype(str)==b].iloc[0]
    candidates=[c for c in left.columns if c in right.columns and c not in _META and pd.api.types.is_numeric_dtype(left[c]) and pd.api.types.is_numeric_dtype(right[c])]
    records=[]
    for c in candidates:
        x,y=pd.to_numeric(row_a[c],errors="coerce"),pd.to_numeric(row_b[c],errors="coerce")
        status="measured" if pd.notna(x) and pd.notna(y) and y!=0 else ("zero denominator" if y==0 else "missing")
        records.append({"Component":c,"Numerator":x,"Denominator":y,"Observed ratio":x/y if status=="measured" else np.nan,"Status":status})
    table=pd.DataFrame(records)
    render_hint("Интерпретируйте это как C₁/C₂. Для equilibrium D нужны Assemblage, CompositionSet и выбранная литературная модель — они будут отдельным следующим режимом.")
    st.dataframe(table,width="stretch",hide_index=True)
    plotted=table.loc[table["Status"]=="measured"].copy()
    if not plotted.empty:
        fig=go.Figure(go.Scatter(x=plotted["Component"],y=np.log10(plotted["Observed ratio"]),mode="lines+markers",name="log10(C₁/C₂)"))
        fig.update_layout(yaxis_title="log10 observed ratio",xaxis_title="",height=380,margin=dict(l=30,r=20,t=20,b=60))
        st.plotly_chart(fig,width="stretch")
    st.download_button("Скачать observed ratios (CSV)",table.to_csv(index=False).encode("utf-8-sig"),"observed_ratios.csv","text/csv")

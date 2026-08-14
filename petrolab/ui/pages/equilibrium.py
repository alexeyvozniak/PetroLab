from __future__ import annotations
import pandas as pd
import streamlit as st
from petrolab.db import list_accessible_datasets, load_dataset_dataframe
from petrolab.scientific_context import add_assemblage_members, create_assemblage, list_assemblages
from petrolab.ui.project_context import active_project_id
from petrolab.ui.layout import render_page_header, render_hint

def render_equilibrium_page() -> None:
    render_page_header("Равновесные пары", "Выберите конкретные анализы, а не все точки одной породы. Это основа для Kd и парной термобарометрии.", eyebrow="Исследование")
    project_id=active_project_id()
    if project_id is None: st.info("Сначала выберите проект."); return
    datasets=list_accessible_datasets(project_id)
    if not datasets: st.info("В проекте пока нет анализов."); return
    render_hint("Сначала создайте candidate-ассоциацию. После петрографической проверки её можно считать равновесной.")
    labels={f"{d['name']} · {d['mineral_key']}":d for d in datasets}
    selected=st.multiselect("Наборы",list(labels),default=list(labels)[:1])
    frames=[load_dataset_dataframe(int(labels[x]['id'])) for x in selected]
    data=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    if data.empty: return
    ids=data['_analysis_id'].astype(str).tolist()
    chosen=st.multiselect("Точки",ids)
    name=st.text_input("Название",placeholder="Напр.: PG-6, Cpx rim + glass")
    phases={int(d['id']):str(d['mineral_key']) for d in datasets}
    if st.button("Создать ассоциацию",type="primary",disabled=not chosen or not name.strip()):
        aid=create_assemblage(project_id,name,equilibrium_status="candidate")
        add_assemblage_members(aid,[{"analysis_id":value,"phase":phases[int(data.loc[data['_analysis_id'].astype(str)==value,'_dataset_id'].iloc[0])]} for value in chosen])
        st.success("Ассоциация создана. Она пока имеет статус candidate.")
    rows=list_assemblages(project_id)
    if rows: st.dataframe(pd.DataFrame(rows)[['name','equilibrium_status','member_count','updated_at']],hide_index=True,width="stretch")

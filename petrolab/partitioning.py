"""Partition-model registry.  Fixed values are never presented as universal constants."""
from __future__ import annotations
import json
from typing import Mapping
from petrolab.db import _utcnow, connect

MODEL_KINDS={"fixed_table","empirical","lattice_strain","ptx_dependent"}
def create_partition_model(name:str,mineral:str,counter_phase:str,model_kind:str,values:Mapping[str,object],*,source:Mapping[str,object],applicability:Mapping[str,object]|None=None)->int:
    if model_kind not in MODEL_KINDS: raise ValueError("Неизвестный тип PartitionModel")
    if not name.strip() or not mineral.strip() or not counter_phase.strip() or not values: raise ValueError("Модель требует название, фазы и коэффициенты")
    if not source.get("citation") and not source.get("doi"): raise ValueError("Для литературной модели обязателен источник или DOI")
    with connect() as con:
        cur=con.execute("INSERT INTO partition_models(name,mineral,counter_phase,model_kind,values_json,source_json,applicability_json,created_at) VALUES(?,?,?,?,?,?,?,?)",(name.strip(),mineral.strip(),counter_phase.strip(),model_kind,json.dumps(dict(values),ensure_ascii=False),json.dumps(dict(source),ensure_ascii=False),json.dumps(dict(applicability or {}),ensure_ascii=False),_utcnow()))
        con.commit(); return int(cur.lastrowid)
def list_partition_models(mineral:str|None=None,counter_phase:str|None=None)->list[dict]:
    clauses=[]; args=[]
    if mineral: clauses.append("mineral=?"); args.append(mineral)
    if counter_phase: clauses.append("counter_phase=?"); args.append(counter_phase)
    with connect() as con: rows=con.execute("SELECT * FROM partition_models"+(" WHERE "+" AND ".join(clauses) if clauses else "")+" ORDER BY name",args).fetchall()
    out=[]
    for row in rows:
        d=dict(row); d["values"]=json.loads(d.pop("values_json")); d["source"]=json.loads(d.pop("source_json")); d["applicability"]=json.loads(d.pop("applicability_json")); out.append(d)
    return out

RECONSTRUCTION_MODES={"recommended","proxy","exploratory"}
def reconstruction_qc(mode:str, *, has_measured_melt:bool, equilibrium_confirmed:bool, source_kind:str)->dict:
    """Never blocks a reconstruction; makes the strength of its assumptions explicit."""
    if mode not in RECONSTRUCTION_MODES: raise ValueError("Неизвестный режим реконструкции")
    warnings=[]
    if not has_measured_melt: warnings.append("Нет измеренного glass/melt inclusion; использован proxy расплава")
    if not equilibrium_confirmed: warnings.append("Равновесие пары не подтверждено")
    if source_kind in {"whole_rock","matrix"}: warnings.append(f"{source_kind} не идентичен расплаву и хранится как явное допущение")
    status="PASS" if mode=="recommended" and not warnings else ("WARNING" if mode!="exploratory" else "EXPLORATORY")
    return {"status":status,"warnings":warnings,"mode":mode}


def assess_model_context(model: Mapping[str, object], rock_context: str | None = None) -> dict[str, str]:
    """Describe applicability in Russian without hiding or blocking a model."""
    declared = str(dict(model.get("applicability") or {}).get("rock") or "").strip()
    selected = (rock_context or "").strip()
    if not selected:
        return {"status": "контекст не задан", "message": "Контекст породы не задан"}
    if declared and declared.casefold() == selected.casefold():
        return {"status": "соответствует", "message": "Литология совпадает с заявленной областью модели"}
    if not declared:
        return {"status": "контекст не указан", "message": "Для модели не указана литология применения"}
    return {
        "status": "предупреждение",
        "message": f"Модель заявлена для породы «{declared}», а выбран контекст «{selected}».",
    }

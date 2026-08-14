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

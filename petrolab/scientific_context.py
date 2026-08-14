"""Provenance-bearing inputs shared by thermobarometry and partitioning."""
from __future__ import annotations

import json
from typing import Iterable, Mapping

from petrolab.db import _utcnow, connect

COMPOSITION_KINDS = {"bulk_xrf", "bulk_icp", "glass", "matrix", "melt_inclusion", "reconstructed_melt"}
EQUILIBRIUM_STATUSES = {"unreviewed", "candidate", "accepted", "rejected"}

def create_composition_set(project_id: int, name: str, kind: str, values: Mapping[str, object], *, units: Mapping[str, str] | None = None, provenance: Mapping[str, object] | None = None, rock_id: int | None = None) -> int:
    if kind not in COMPOSITION_KINDS: raise ValueError(f"Неизвестный тип CompositionSet: {kind}")
    if not name.strip() or not values: raise ValueError("CompositionSet требует название и хотя бы один измеренный компонент")
    now = _utcnow()
    with connect() as con:
        cur = con.execute("INSERT INTO composition_sets(project_id,rock_id,name,kind,values_json,units_json,provenance_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (int(project_id),rock_id,name.strip(),kind,json.dumps(dict(values),ensure_ascii=False),json.dumps(dict(units or {}),ensure_ascii=False),json.dumps(dict(provenance or {}),ensure_ascii=False),now,now))
        con.commit(); return int(cur.lastrowid)

def create_assemblage(project_id: int, name: str, *, equilibrium_status: str = "unreviewed", note: str = "") -> int:
    if equilibrium_status not in EQUILIBRIUM_STATUSES: raise ValueError("Неизвестный статус равновесия")
    if not name.strip(): raise ValueError("У ассоциации должно быть название")
    now = _utcnow()
    with connect() as con:
        cur=con.execute("INSERT INTO assemblages(project_id,name,equilibrium_status,note,created_at,updated_at) VALUES(?,?,?,?,?,?)",(int(project_id),name.strip(),equilibrium_status,note.strip(),now,now)); con.commit(); return int(cur.lastrowid)

def add_assemblage_members(assemblage_id: int, members: Iterable[Mapping[str, object]]) -> None:
    rows=list(members)
    if not rows: raise ValueError("Выберите хотя бы один анализ")
    with connect() as con:
        for member in rows:
            analysis_id, phase=str(member.get("analysis_id","")),str(member.get("phase",""))
            if not analysis_id or not phase: raise ValueError("Для члена ассоциации обязательны analysis_id и фаза")
            if not con.execute("SELECT 1 FROM analysis_rows WHERE analysis_id=?",(analysis_id,)).fetchone(): raise ValueError(f"Анализ не найден: {analysis_id}")
            con.execute("INSERT OR REPLACE INTO assemblage_members(assemblage_id,analysis_id,phase,role,generation,pair_group,note) VALUES(?,?,?,?,?,?,?)",(int(assemblage_id),analysis_id,phase,str(member.get("role","")),str(member.get("generation","")),str(member.get("pair_group","")),str(member.get("note",""))))
        con.execute("UPDATE assemblages SET updated_at=? WHERE id=?",(_utcnow(),int(assemblage_id))); con.commit()

def list_assemblages(project_id: int) -> list[dict]:
    with connect() as con:
        rows=con.execute("SELECT a.*,COUNT(m.analysis_id) AS member_count FROM assemblages a LEFT JOIN assemblage_members m ON m.assemblage_id=a.id WHERE a.project_id=? GROUP BY a.id ORDER BY a.updated_at DESC",(int(project_id),)).fetchall()
    return [dict(row) for row in rows]

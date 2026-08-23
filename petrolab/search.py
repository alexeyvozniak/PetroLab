"""Global project-aware search over stored samples, analyses and images."""
from __future__ import annotations

import json
from collections.abc import Iterable

from petrolab.db import connect, list_datasets
from petrolab.services.image_service import image_export_records


SEARCH_FIELDS = ("Sample", "Образец", "Grain", "Зерно", "Point", "Точка", "Mineral", "Минерал", "Rock", "Порода", "Massif", "Массив", "Source", "Источник")


def _contains(value: object, needle: str) -> bool:
    return needle in str(value or "").casefold()


def global_search(query: str, *, project_ids: Iterable[int] | None = None, limit: int = 200) -> list[dict]:
    """Return direct navigation targets; raw chemical values are never altered."""
    needle = str(query).strip().casefold()
    if len(needle) < 2:
        return []
    allowed = {int(value) for value in project_ids} if project_ids is not None else None
    datasets = list_datasets()
    dataset_by_id = {int(row["id"]): row for row in datasets}
    results: list[dict] = []
    with connect() as con:
        rows = con.execute(
            """SELECT a.analysis_id,a.dataset_id,a.data_json,d.name AS dataset_name,p.id AS project_id,p.name AS project_name
               FROM analysis_rows a JOIN datasets d ON d.id=a.dataset_id JOIN projects p ON p.id=d.project_id
               ORDER BY a.updated_at DESC"""
        ).fetchall()
    for row in rows:
        if allowed is not None and int(row["project_id"]) not in allowed:
            continue
        try:
            payload = json.loads(str(row["data_json"]))
        except json.JSONDecodeError:
            payload = {}
        searchable = [row["dataset_name"], row["project_name"], *[payload.get(field, "") for field in SEARCH_FIELDS]]
        if not any(_contains(value, needle) for value in searchable):
            continue
        labels = [str(payload.get(field)).strip() for field in SEARCH_FIELDS if str(payload.get(field, "")).strip()]
        results.append({
            "kind": "analysis", "analysis_id": str(row["analysis_id"]), "dataset_id": int(row["dataset_id"]),
            "project_id": int(row["project_id"]), "project_name": str(row["project_name"]),
            "title": " · ".join(labels[:3]) or str(row["dataset_name"]), "detail": f"Анализ · {row['dataset_name']}",
        })
        if len(results) >= int(limit):
            return results
    for image in image_export_records():
        project_id = int(image.get("project_id") or 0)
        if allowed is not None and project_id not in allowed:
            continue
        fields = [image.get("title"), image.get("original_filename"), image.get("kind"), image.get("scope_value"), image.get("project_name")]
        if not any(_contains(value, needle) for value in fields):
            continue
        results.append({
            "kind": "image", "asset_id": int(image["id"]), "dataset_id": image.get("dataset_id"),
            "project_id": project_id, "project_name": str(image.get("project_name") or ""),
            "title": str(image.get("title") or image.get("original_filename")), "detail": f"Изображение · {image.get('kind') or 'без типа'}",
        })
        if len(results) >= int(limit):
            break
    return results

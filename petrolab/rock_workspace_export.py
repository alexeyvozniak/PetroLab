from __future__ import annotations

import io
import json
import math
from typing import Any

import pandas as pd

from petrolab.rock_workspace_model import RockWorkspaceSnapshot


def _json_value(value: Any):
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if hasattr(value, "item"):
        try:
            return _json_value(value.item())
        except Exception:
            pass
    return value


def rock_sample_card_payload(snapshot: RockWorkspaceSnapshot) -> dict:
    rock = {
        str(key): _json_value(value)
        for key, value in snapshot.rock.items()
        if str(key) not in {"project_id"}
    }
    chemistry = []
    for _, row in snapshot.composition.iterrows():
        chemistry.append({str(key): _json_value(value) for key, value in row.items()})
    isotopes = []
    for _, row in snapshot.isotopes.iterrows():
        isotopes.append({str(key): _json_value(value) for key, value in row.items()})
    datasets = [
        {
            "id": int(item["id"]),
            "name": str(item.get("name") or ""),
            "mineral_key": str(item.get("mineral_key") or ""),
            "source_filename": str(item.get("source_filename") or ""),
            "row_count": int(item.get("row_count") or 0),
            "linked_to_project": bool(item.get("linked_to_project")),
        }
        for item in snapshot.linked_datasets
    ]
    images = [
        {
            "id": int(item["id"]),
            "kind": str(item.get("kind") or ""),
            "title": str(item.get("title") or ""),
            "original_filename": str(item.get("original_filename") or ""),
        }
        for item in snapshot.images
    ]
    return {
        "schema_version": 1,
        "kind": "petrolab_rock_sample_card",
        "rock": rock,
        "data_health": {
            "major_present": int(snapshot.major_present),
            "major_expected": int(snapshot.major_expected),
            "trace_count": int(snapshot.trace_count),
            "isotope_systems": list(snapshot.isotope_systems),
            "warnings": list(snapshot.warnings),
        },
        "chemistry": chemistry,
        "isotopes": isotopes,
        "mineral_datasets": datasets,
        "images": images,
    }


def rock_sample_card_json_bytes(snapshot: RockWorkspaceSnapshot) -> bytes:
    return json.dumps(
        rock_sample_card_payload(snapshot),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def rock_sample_card_xlsx_bytes(snapshot: RockWorkspaceSnapshot) -> bytes:
    buffer = io.BytesIO()
    rock_rows = [
        {"field": key, "value": _json_value(value)}
        for key, value in snapshot.rock.items()
        if str(key) != "project_id"
    ]
    health_rows = [
        {"metric": "major", "value": f"{snapshot.major_present}/{snapshot.major_expected}"},
        {"metric": "trace_count", "value": snapshot.trace_count},
        {"metric": "isotope_systems", "value": " | ".join(snapshot.isotope_systems)},
        {"metric": "warnings", "value": " | ".join(snapshot.warnings)},
    ]
    datasets = pd.DataFrame([
        {
            "id": int(item["id"]),
            "name": str(item.get("name") or ""),
            "mineral_key": str(item.get("mineral_key") or ""),
            "source_filename": str(item.get("source_filename") or ""),
            "row_count": int(item.get("row_count") or 0),
            "linked_to_project": bool(item.get("linked_to_project")),
        }
        for item in snapshot.linked_datasets
    ])
    images = pd.DataFrame([
        {
            "id": int(item["id"]),
            "kind": str(item.get("kind") or ""),
            "title": str(item.get("title") or ""),
            "original_filename": str(item.get("original_filename") or ""),
        }
        for item in snapshot.images
    ])
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(rock_rows).to_excel(writer, index=False, sheet_name="Rock")
        snapshot.composition.to_excel(writer, index=False, sheet_name="Chemistry")
        snapshot.isotopes.to_excel(writer, index=False, sheet_name="Isotopes")
        datasets.to_excel(writer, index=False, sheet_name="Mineral datasets")
        images.to_excel(writer, index=False, sheet_name="Images")
        pd.DataFrame(health_rows).to_excel(writer, index=False, sheet_name="Data health")
    return buffer.getvalue()

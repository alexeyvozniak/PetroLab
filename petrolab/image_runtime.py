from __future__ import annotations

import json


def _field_exists(con, dataset_id: int, column: str, value: str) -> bool:
    rows = con.execute(
        "SELECT data_json FROM analysis_rows WHERE dataset_id=?", (int(dataset_id),)
    ).fetchall()
    for row in rows:
        try:
            data = json.loads(row["data_json"])
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        if column in data and str(data.get(column)) == str(value):
            return True
    return False


def install() -> None:
    from petrolab.db import connect
    from petrolab.repositories import image_repository as repo

    original_get = repo.get_image_record
    original_list = repo.list_image_records

    def annotate(record: dict) -> dict:
        result = dict(record)
        scope = str(result.get("scope_type") or "")
        ids = list(result.get("analysis_ids") or [])
        status = "ok"
        reason = ""
        if scope == "Точки анализа" and not ids:
            status = "detached"
            reason = "Связанные аналитические точки больше не существуют."
        elif scope == "Значение поля":
            dataset_id = result.get("dataset_id")
            column = str(result.get("scope_column") or "")
            value = str(result.get("scope_value") or "")
            with connect() as con:
                valid = bool(dataset_id and column and _field_exists(con, int(dataset_id), column, value))
            if not valid:
                status = "detached"
                reason = f"В текущем наборе больше нет связи {column} = {value}."
        result["link_status"] = status
        result["link_status_reason"] = reason
        return result

    def get_image_record(asset_id: int) -> dict:
        return annotate(original_get(int(asset_id)))

    def list_image_records(*, project_id=None, dataset_id=None, analysis_id=None):
        records = original_list(
            project_id=project_id, dataset_id=dataset_id, analysis_id=analysis_id
        )
        return [annotate(record) for record in records]

    repo.get_image_record = get_image_record
    repo.list_image_records = list_image_records

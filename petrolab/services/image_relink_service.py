from __future__ import annotations

from petrolab.db import dataset_is_accessible, get_analysis_record
from petrolab.repositories.image_repository import get_image_record, replace_image_analysis_links


def relink_image_asset(asset_id: int, analysis_ids: list[str]) -> None:
    """Relink a point image to analyses anywhere in the image's working project.

    Point images follow immutable analysis IDs. After a mixed dataset is split, those analyses
    legitimately live in new phase datasets, so requiring the original raw dataset would make an
    otherwise valid BSE/photo link impossible to edit. Project membership is the correct boundary.
    """
    record = get_image_record(int(asset_id))
    project_id = int(record["project_id"])
    unique_ids = tuple(dict.fromkeys(str(value).strip() for value in analysis_ids if str(value).strip()))
    if not unique_ids:
        raise ValueError("Не выбрана ни одна аналитическая точка")

    for analysis_id in unique_ids:
        analysis = get_analysis_record(analysis_id)
        if not dataset_is_accessible(project_id, int(analysis["dataset_id"])):
            raise ValueError(
                f"Аналитическая точка {analysis_id[:8]} находится вне рабочего проекта изображения"
            )
    replace_image_analysis_links(int(asset_id), unique_ids)

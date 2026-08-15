from __future__ import annotations

from pathlib import Path

from petrolab.repositories.rock_repository import list_rocks
from petrolab.services.image_service import list_all_images
from petrolab.services.rock_image_service import list_rock_images
from petrolab.slides import list_slide_images


def _existing_path(*values: object) -> Path | None:
    for value in values:
        text = str(value or "").strip()
        if not text:
            continue
        path = Path(text)
        if path.is_file():
            return path
    return None


def _source(
    *,
    source_id: str,
    source_name: str,
    group: str,
    path: Path,
    note: str = "",
) -> dict:
    return {
        "source_id": str(source_id),
        "source_name": str(source_name),
        "group": str(group),
        "path": str(path),
        "note": str(note),
    }


def project_publication_sources(project_id: int) -> list[dict]:
    """Return local project images that can be used as publication panels.

    The adapter returns file references, not image bytes, so simply opening the
    publication page never loads every project image into memory. Bytes are read
    only for panels the user actually selected.
    """
    project_id = int(project_id)
    sources: list[dict] = []

    # Images attached to analytical datasets.
    for record in list_all_images():
        try:
            record_project_id = int(record.get("project_id"))
        except (TypeError, ValueError):
            continue
        if record_project_id != project_id:
            continue
        path = _existing_path(record.get("stored_path"))
        if path is None:
            continue
        title = str(record.get("title") or record.get("original_filename") or path.name)
        kind = str(record.get("kind") or "Изображение анализа")
        sources.append(_source(
            source_id=f"analysis_image:{int(record['id'])}",
            source_name=f"{title} · {kind}",
            group="Анализы и минералы",
            path=path,
        ))

    # General rock photographs.
    for rock in list_rocks(project_id):
        rock_id = int(rock["id"])
        rock_name = str(rock.get("name") or f"Порода {rock_id}")
        for image in list_rock_images(rock_id):
            path = _existing_path(image.get("stored_path"))
            if path is None:
                continue
            title = str(image.get("title") or image.get("original_filename") or path.name)
            kind = str(image.get("kind") or "Фото породы")
            sources.append(_source(
                source_id=f"rock_image:{int(image['id'])}",
                source_name=f"{rock_name} · {title} · {kind}",
                group="Породы",
                path=path,
            ))

    # Thin-section images: prefer the master; fall back to the persistent preview
    # when a linked original has moved or is temporarily unavailable.
    for image in list_slide_images(project_id):
        master = _existing_path(image.managed_path, image.source_path)
        preview = _existing_path(image.preview_path)
        path = master or preview
        if path is None:
            continue
        fallback = master is None and preview is not None
        note = "Используется preview: оригинал шлифа сейчас недоступен" if fallback else ""
        title = str(image.title or image.original_filename or f"Шлиф {image.id}")
        sources.append(_source(
            source_id=f"slide_image:{int(image.id)}",
            source_name=f"{title} · {image.image_type}",
            group="Шлифы",
            path=path,
            note=note,
        ))

    # Stable grouping/order makes the multiselect deterministic across reruns.
    sources.sort(key=lambda row: (str(row["group"]), str(row["source_name"]).casefold(), str(row["source_id"])))
    return sources


def source_bytes(source: dict) -> bytes:
    path = _existing_path(source.get("path"))
    if path is None:
        raise FileNotFoundError(f"Источник панели больше недоступен: {source.get('source_name', '')}")
    return path.read_bytes()

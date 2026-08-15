from __future__ import annotations

import json
import re
import unicodedata
import zipfile
from pathlib import Path
from typing import Iterable

_SEPARATOR_RE = re.compile(r"[\s_\-–—./\\]+", re.UNICODE)


def normalize_project_key(value: str) -> str:
    """Conservative key used only to suggest a destination project.

    A matching key is never permission to merge projects or Samples silently.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip().casefold()
    text = _SEPARATOR_RE.sub("", text)
    return "".join(ch for ch in text if ch.isalnum())


def suggested_project_ids(projects: Iterable[dict], incoming_name: str) -> tuple[int, ...]:
    """Return existing projects that look like the incoming project context."""
    incoming = str(incoming_name or "").strip()
    if not incoming:
        return ()
    incoming_folded = incoming.casefold()
    incoming_key = normalize_project_key(incoming)
    exact: list[int] = []
    normalized: list[int] = []
    for project in projects:
        try:
            project_id = int(project["id"])
        except (KeyError, TypeError, ValueError):
            continue
        name = str(project.get("name") or "").strip()
        if not name:
            continue
        if name.casefold() == incoming_folded:
            exact.append(project_id)
        elif incoming_key and normalize_project_key(name) == incoming_key:
            normalized.append(project_id)
    return tuple(exact + normalized)


def preferred_project_id(
    projects: Iterable[dict],
    incoming_name: str,
    *,
    active_project_id: int | None = None,
) -> int | None:
    """Prefer one unambiguous name match, otherwise keep the user's active context."""
    items = list(projects)
    matches = suggested_project_ids(items, incoming_name)
    if len(matches) == 1:
        return int(matches[0])
    available = {int(project["id"]) for project in items if project.get("id") is not None}
    if active_project_id is not None and int(active_project_id) in available:
        return int(active_project_id)
    return int(items[0]["id"]) if items else None


def read_archive_context_hint(archive_path: str | Path) -> tuple[str, str]:
    """Read only the portable manifest to choose a destination before full validation."""
    source = Path(archive_path).expanduser().resolve()
    with zipfile.ZipFile(source, "r") as archive:
        try:
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        except KeyError as exc:
            raise ValueError("В архиве отсутствует manifest.json") from exc
    project = manifest.get("project") or {}
    incoming_name = str(project.get("name") or "").strip()
    if not incoming_name:
        raise ValueError("В переносимом пакете не указан проектный контекст")
    payload_kind = str(manifest.get("payload_kind") or "project")
    return incoming_name, payload_kind

"""Совместить whole-rock staging из #71 с актуальным рабочим пространством пород."""
from __future__ import annotations

from . import rocks as _rocks
from . import rocks_v0154 as _staging


def render_rocks_page() -> None:
    """Подменить только массовый импорт, не откатывая более новый интерфейс пород."""
    try:
        from .v0154_rock_workspace_wrappers import render_rocks_page as render_current_rocks
    except ImportError:
        render_current_rocks = _rocks.render_rocks_page

    original = _rocks._render_bulk_import

    def replacement(project_id: int) -> None:
        _staging._staged_bulk_import(int(project_id), original)

    _rocks._render_bulk_import = replacement
    try:
        render_current_rocks()
    finally:
        _rocks._render_bulk_import = original

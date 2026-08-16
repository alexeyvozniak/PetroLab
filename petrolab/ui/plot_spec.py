from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, MutableMapping


CURRENT_PLOT_SPEC_KEY = "_petrolab_current_plot_spec"
MULTI_PANEL_INBOX_KEY = "_petrolab_multi_panel_inbox"
MULTI_PANEL_VISIBLE_SERIES_KEY = "_multi_panel_incoming_visible_series"


@dataclass(frozen=True)
class PlotSpec:
    dataset_ids: tuple[int, ...]
    analysis_ids: tuple[str, ...]
    x: str
    y: str
    group_column: str = ""
    x_label: str = ""
    y_label: str = ""
    title: str = ""
    log_x: bool = False
    log_y: bool = False
    visible_sources: tuple[str, ...] = ()
    hidden_sources: tuple[str, ...] = ()
    visible_series: tuple[str, ...] = ()
    style_map: dict[str, dict[str, Any]] = field(default_factory=dict)
    marker_size: float = 0.0
    figure_preset: str = ""
    show_grid: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["dataset_ids"] = list(self.dataset_ids)
        payload["analysis_ids"] = list(self.analysis_ids)
        payload["visible_sources"] = list(self.visible_sources)
        payload["hidden_sources"] = list(self.hidden_sources)
        payload["visible_series"] = list(self.visible_series)
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "PlotSpec":
        return cls(
            dataset_ids=tuple(int(value) for value in raw.get("dataset_ids", ()) if value is not None),
            analysis_ids=tuple(str(value) for value in raw.get("analysis_ids", ()) if str(value)),
            x=str(raw.get("x") or ""),
            y=str(raw.get("y") or ""),
            group_column=str(raw.get("group_column") or ""),
            x_label=str(raw.get("x_label") or raw.get("x") or ""),
            y_label=str(raw.get("y_label") or raw.get("y") or ""),
            title=str(raw.get("title") or ""),
            log_x=bool(raw.get("log_x", False)),
            log_y=bool(raw.get("log_y", False)),
            visible_sources=tuple(str(value) for value in raw.get("visible_sources", ()) if str(value)),
            hidden_sources=tuple(str(value) for value in raw.get("hidden_sources", ()) if str(value)),
            visible_series=tuple(str(value) for value in raw.get("visible_series", ()) if str(value)),
            style_map={str(key): dict(value) for key, value in dict(raw.get("style_map") or {}).items()},
            marker_size=float(raw.get("marker_size", 0.0) or 0.0),
            figure_preset=str(raw.get("figure_preset") or ""),
            show_grid=bool(raw.get("show_grid", False)),
        )


def _state(state: MutableMapping[str, Any] | None = None) -> MutableMapping[str, Any]:
    if state is not None:
        return state
    import streamlit as st

    return st.session_state


def _appearance_defaults() -> tuple[str, bool]:
    try:
        from petrolab.settings_service import load_settings
        from petrolab.visualization_presets import FIGURE_PRESETS

        preset_name = str(load_settings().get("default_figure_preset", "Lithos"))
        preset = FIGURE_PRESETS.get(preset_name, FIGURE_PRESETS.get("Lithos"))
        return preset_name, bool(getattr(preset, "grid", False))
    except Exception:
        return "", False


def _known_multi_panel_preset(name: str) -> str:
    """Return a preset only when the multi-panel workspace can actually render it."""
    try:
        from petrolab.visualization_presets import FIGURE_PRESETS

        value = str(name or "")
        return value if value in FIGURE_PRESETS else ""
    except Exception:
        return ""


def normalize_plot_spec(
    spec: PlotSpec,
    state: MutableMapping[str, Any] | None = None,
    *,
    default_preset: str | None = None,
    default_grid: bool | None = None,
) -> PlotSpec:
    """Complete a PlotSpec at the canonical XY → multi-panel boundary.

    Older callers do not know the newer appearance fields. They remain valid:
    the current quick-plot widget state and configured figure preset fill only
    fields that are absent. Explicit values in ``spec`` always win.
    """
    store = _state(state)
    visible_series = spec.visible_series
    if not visible_series and spec.group_column and spec.style_map:
        visible_series = tuple(str(value) for value in spec.style_map if str(value))

    marker_size = float(spec.marker_size or 0.0)
    if marker_size <= 0:
        try:
            marker_size = float(store.get("quick_marker_size") or 0.0)
        except (TypeError, ValueError):
            marker_size = 0.0

    preset_name = str(spec.figure_preset or "")
    grid = bool(spec.show_grid)
    if not preset_name:
        if default_preset is None or default_grid is None:
            resolved_preset, resolved_grid = _appearance_defaults()
        else:
            resolved_preset, resolved_grid = str(default_preset), bool(default_grid)
        preset_name = str(default_preset if default_preset is not None else resolved_preset)
        grid = bool(default_grid if default_grid is not None else resolved_grid)

    return replace(
        spec,
        visible_series=tuple(visible_series),
        marker_size=max(0.0, marker_size),
        figure_preset=preset_name,
        show_grid=grid,
    )


def _seed_multi_panel_appearance(spec: PlotSpec, store: MutableMapping[str, Any]) -> None:
    """Seed only valid multi-panel widget defaults; preserve richer spec metadata separately."""
    if spec.marker_size > 0:
        store["multi_panel_marker"] = int(round(spec.marker_size))
    compatible_preset = _known_multi_panel_preset(spec.figure_preset)
    if compatible_preset:
        store["multi_panel_preset"] = compatible_preset
    else:
        store.pop("multi_panel_preset", None)
    store["multi_panel_grid"] = bool(spec.show_grid)
    if spec.visible_series:
        store[MULTI_PANEL_VISIBLE_SERIES_KEY] = list(spec.visible_series)
    else:
        store.pop(MULTI_PANEL_VISIBLE_SERIES_KEY, None)


def set_current_plot_spec(spec: PlotSpec, state: MutableMapping[str, Any] | None = None) -> None:
    store = _state(state)
    normalized = normalize_plot_spec(spec, store)
    store[CURRENT_PLOT_SPEC_KEY] = normalized.to_dict()


def read_current_plot_spec(state: MutableMapping[str, Any] | None = None) -> PlotSpec | None:
    raw = _state(state).get(CURRENT_PLOT_SPEC_KEY)
    return PlotSpec.from_dict(raw) if isinstance(raw, dict) else None


def send_to_multi_panel(spec: PlotSpec, state: MutableMapping[str, Any] | None = None) -> None:
    store = _state(state)
    normalized = normalize_plot_spec(spec, store)
    store[MULTI_PANEL_INBOX_KEY] = normalized.to_dict()
    _seed_multi_panel_appearance(normalized, store)


def peek_multi_panel_inbox(state: MutableMapping[str, Any] | None = None) -> PlotSpec | None:
    raw = _state(state).get(MULTI_PANEL_INBOX_KEY)
    return PlotSpec.from_dict(raw) if isinstance(raw, dict) else None


def clear_multi_panel_inbox(state: MutableMapping[str, Any] | None = None) -> None:
    _state(state).pop(MULTI_PANEL_INBOX_KEY, None)

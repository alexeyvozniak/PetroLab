from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, MutableMapping


CURRENT_PLOT_SPEC_KEY = "_petrolab_current_plot_spec"
MULTI_PANEL_INBOX_KEY = "_petrolab_multi_panel_inbox"


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


def set_current_plot_spec(spec: PlotSpec, state: MutableMapping[str, Any] | None = None) -> None:
    _state(state)[CURRENT_PLOT_SPEC_KEY] = spec.to_dict()


def read_current_plot_spec(state: MutableMapping[str, Any] | None = None) -> PlotSpec | None:
    raw = _state(state).get(CURRENT_PLOT_SPEC_KEY)
    return PlotSpec.from_dict(raw) if isinstance(raw, dict) else None


def send_to_multi_panel(spec: PlotSpec, state: MutableMapping[str, Any] | None = None) -> None:
    _state(state)[MULTI_PANEL_INBOX_KEY] = spec.to_dict()


def peek_multi_panel_inbox(state: MutableMapping[str, Any] | None = None) -> PlotSpec | None:
    raw = _state(state).get(MULTI_PANEL_INBOX_KEY)
    return PlotSpec.from_dict(raw) if isinstance(raw, dict) else None


def clear_multi_panel_inbox(state: MutableMapping[str, Any] | None = None) -> None:
    _state(state).pop(MULTI_PANEL_INBOX_KEY, None)

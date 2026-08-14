from __future__ import annotations

import math
from typing import Mapping

import numpy as np
import pandas as pd
import plotly.graph_objects as go

REE_ORDER = ("La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu")
# Shannon (1976), eightfold coordination, Å; used only for an Onuma display.
REE_RADII_8 = {
    "La": 1.160, "Ce": 1.143, "Pr": 1.126, "Nd": 1.109, "Sm": 1.079,
    "Eu": 1.066, "Gd": 1.053, "Tb": 1.040, "Dy": 1.027, "Ho": 1.015,
    "Er": 1.004, "Tm": 0.994, "Yb": 0.985, "Lu": 0.977,
}

def kd_table(values: Mapping[str, object], metadata: Mapping[str, object]) -> pd.DataFrame:
    rows = []
    for element, raw_value in values.items():
        raw = dict(metadata.get(element, {}) or {})
        value = raw.get("value", raw_value if isinstance(raw_value, (int, float)) else np.nan)
        rows.append({
            "Element": str(element), "Kd": pd.to_numeric(value, errors="coerce"),
            "σ": pd.to_numeric(raw.get("sd"), errors="coerce"),
            "low": pd.to_numeric(raw.get("low"), errors="coerce"),
            "high": pd.to_numeric(raw.get("high"), errors="coerce"),
        })
    return pd.DataFrame(rows)

def _ree_frame(table: pd.DataFrame) -> pd.DataFrame:
    out = table.copy()
    out["Element"] = out["Element"].astype(str).str.replace(r"\d+$", "", regex=True)
    out = out[out["Element"].isin(REE_ORDER)].drop_duplicates("Element")
    out["order"] = out["Element"].map({element: i for i, element in enumerate(REE_ORDER)})
    return out.sort_values("order")

def ree_d_figure(table: pd.DataFrame, name: str) -> go.Figure:
    frame = _ree_frame(table)
    fig = go.Figure()
    if not frame.empty:
        fig.add_trace(go.Scatter(
            x=frame["Element"], y=frame["Kd"], mode="lines+markers", name=name,
            marker={"size": 10}, line={"width": 2.4},
            error_y={"type": "data", "array": frame["σ"], "visible": frame["σ"].notna().any()},
            customdata=np.stack([frame["low"].fillna(np.nan), frame["high"].fillna(np.nan)], axis=-1),
            hovertemplate="%{x}<br>Kd=%{y:.4g}<br>low=%{customdata[0]:.4g}<br>high=%{customdata[1]:.4g}<extra></extra>",
        ))
    fig.update_layout(template="plotly_white", height=410, margin=dict(l=44, r=18, t=36, b=44),
                      title="REE partition coefficients", yaxis={"type": "log", "title": "Kd"})
    return fig

def onuma_figure(table: pd.DataFrame, name: str) -> go.Figure:
    frame = _ree_frame(table)
    frame["radius"] = frame["Element"].map(REE_RADII_8)
    frame = frame[(frame["Kd"] > 0) & frame["radius"].notna()].copy()
    fig = go.Figure()
    if not frame.empty:
        fig.add_trace(go.Scatter(
            x=frame["radius"], y=np.log(frame["Kd"]), text=frame["Element"],
            mode="markers+text", textposition="top center", name=name,
            marker={"size": 11, "color": "#4c78a8"},
            hovertemplate="%{text}<br>r(VIII)=%{x:.3f} Å<br>ln Kd=%{y:.4g}<extra></extra>",
        ))
    fig.update_layout(template="plotly_white", height=410, margin=dict(l=48, r=18, t=36, b=44),
                      title="Onuma plot", xaxis_title="Shannon ionic radius, CN VIII (Å)",
                      yaxis_title="ln Kd")
    return fig

def spider_figure(table: pd.DataFrame, name: str) -> go.Figure:
    frame = table.copy()
    frame["Element"] = frame["Element"].astype(str).str.replace(r"\d+$", "", regex=True)
    priority = ["Rb","Ba","Th","U","Nb","Ta","K","La","Ce","Pb","Sr","P","Nd","Zr","Hf","Sm","Eu","Ti","Tb","Dy","Y","Yb","Lu","Sc","Cr","Ni"]
    frame = frame[frame["Element"].isin(priority)].drop_duplicates("Element")
    frame["order"] = frame["Element"].map({element: i for i, element in enumerate(priority)})
    frame = frame.sort_values("order")
    fig = go.Figure()
    if not frame.empty:
        fig.add_trace(go.Scatter(x=frame["Element"], y=frame["Kd"], mode="lines+markers", name=name, marker={"size": 8}))
    fig.update_layout(template="plotly_white", height=410, margin=dict(l=44,r=18,t=36,b=60),
                      title="Kd spider", yaxis={"type":"log","title":"Kd"})
    return fig

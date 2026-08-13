from __future__ import annotations

from io import BytesIO

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from petrolab.plot_text import matplotlib_label
from petrolab.services.rock_service import rhodes_equilibrium_fo


# Field-boundary vertices after Le Bas et al. (1986) / Le Maitre et al. IUGS TAS.
TAS_SOLID_PATHS: tuple[tuple[tuple[float, float], ...], ...] = (
    ((41, 0), (41, 3), (45, 9.4), (48.4, 11.5), (52.5, 14)),
    ((45, 0), (45, 3), (45, 5), (49.4, 7.3), (53, 9.3), (57.6, 11.7), (61, 13.5)),
    ((45, 5), (52, 5), (57, 5.9), (63, 7), (69, 8), (69, 13.0)),
    ((45, 9.4), (49.4, 7.3), (52, 5), (52, 0)),
    ((48.4, 11.5), (53, 9.3), (57, 5.9), (57, 0)),
    ((52.5, 14), (57.6, 11.7), (63, 7), (63, 0)),
    ((69, 8), (74, 3)),
    ((41, 3), (45, 3)),
)
TAS_DASHED_PATHS: tuple[tuple[tuple[float, float], ...], ...] = (
    ((41, 3), (41, 7), (45, 9.4)),
    ((57, 1.5), (57, 0)),
    ((63, 2), (63, 0)),
    ((74, 3), (76.3, 0)),
)
TAS_LABELS = {
    "Foidite": (39.0, 9.0),
    "Picrobasalt": (43.0, 1.4),
    "Basalt": (48.5, 3.0),
    "Basanite/\nTephrite": (43.2, 5.8),
    "Trachybasalt": (47.3, 6.0),
    "Basaltic\nandesite": (54.2, 3.2),
    "Basaltic\ntrachyandesite": (51.0, 7.2),
    "Andesite": (60.0, 3.5),
    "Trachyandesite": (55.5, 8.7),
    "Dacite": (67.0, 4.2),
    "Trachyte/\nTrachydacite": (64.5, 10.0),
    "Rhyolite": (73.0, 8.0),
    "Phonotephrite": (47.2, 10.0),
    "Tephriphonolite": (52.0, 11.2),
    "Phonolite": (57.0, 13.3),
}


def _numeric(dataframe: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(dataframe[column], errors="coerce") if column in dataframe else pd.Series(np.nan, index=dataframe.index)


def build_tas_figure(
    dataframe: pd.DataFrame,
    *,
    group_column: str | None = None,
    label_column: str | None = "Rock",
    font_family: str = "Arial",
    font_size: float = 8.5,
    marker_size: float = 45.0,
    show_labels: bool = True,
    grid: bool = False,
    figure_size: tuple[float, float] = (7.3, 5.6),
):
    work = dataframe.copy()
    work["SiO2"] = _numeric(work, "SiO2")
    work["Total alkalis"] = _numeric(work, "Na2O") + _numeric(work, "K2O")
    work = work.dropna(subset=["SiO2", "Total alkalis"])
    with plt.rc_context({"font.family": font_family, "font.size": font_size}):
        fig, ax = plt.subplots(figsize=figure_size)
        for path in TAS_SOLID_PATHS:
            x, y = zip(*path)
            ax.plot(x, y, color="black", lw=0.9)
        for path in TAS_DASHED_PATHS:
            x, y = zip(*path)
            ax.plot(x, y, color="black", lw=0.8, ls="--")
        if show_labels:
            for text, (x, y) in TAS_LABELS.items():
                ax.text(x, y, text, ha="center", va="center", fontsize=max(6, font_size - 1))
        if group_column and group_column in work.columns:
            for name, subset in work.groupby(group_column, dropna=False, sort=False):
                ax.scatter(subset["SiO2"], subset["Total alkalis"], s=marker_size, label=str(name), zorder=5)
            ax.legend(frameon=False, fontsize=max(6, font_size - 1))
        else:
            ax.scatter(work["SiO2"], work["Total alkalis"], s=marker_size, zorder=5)
        if label_column and label_column in work.columns:
            for _, row in work.iterrows():
                label = str(row.get(label_column, "")).strip()
                if label and label.lower() != "nan":
                    ax.annotate(label, (row["SiO2"], row["Total alkalis"]), xytext=(3, 3), textcoords="offset points", fontsize=max(6, font_size - 1))
        ax.set_xlim(35, 80)
        ax.set_ylim(0, 16)
        ax.set_xlabel(matplotlib_label("SiO₂, wt.%"))
        ax.set_ylabel(matplotlib_label("Na₂O + K₂O, wt.%"))
        ax.set_title("TAS · Le Bas et al. (1986), IUGS")
        if grid:
            ax.grid(True, alpha=0.15)
        fig.tight_layout()
        return fig


def build_rock_scatter(
    dataframe: pd.DataFrame,
    x: str,
    y: str,
    *,
    group_column: str | None = None,
    label_column: str | None = "Rock",
    title: str = "",
    x_label: str | None = None,
    y_label: str | None = None,
    font_family: str = "Arial",
    font_size: float = 9.0,
    marker_size: float = 50.0,
    grid: bool = False,
    figure_size: tuple[float, float] = (7.2, 5.2),
):
    work = dataframe.copy()
    work[x] = _numeric(work, x)
    work[y] = _numeric(work, y)
    work = work.dropna(subset=[x, y])
    with plt.rc_context({"font.family": font_family, "font.size": font_size}):
        fig, ax = plt.subplots(figsize=figure_size)
        if group_column and group_column in work.columns:
            for name, subset in work.groupby(group_column, dropna=False, sort=False):
                ax.scatter(subset[x], subset[y], s=marker_size, label=str(name))
            ax.legend(frameon=False, fontsize=max(6, font_size - 1))
        else:
            ax.scatter(work[x], work[y], s=marker_size)
        if label_column and label_column in work.columns:
            for _, row in work.iterrows():
                label = str(row.get(label_column, "")).strip()
                if label and label.lower() != "nan":
                    ax.annotate(label, (row[x], row[y]), xytext=(3, 3), textcoords="offset points", fontsize=max(6, font_size - 1))
        ax.set_xlabel(matplotlib_label(x_label or x))
        ax.set_ylabel(matplotlib_label(y_label or y))
        ax.set_title(matplotlib_label(title))
        if grid:
            ax.grid(True, alpha=0.2)
        fig.tight_layout()
        return fig


def build_rhodes_figure(
    rock_dataframe: pd.DataFrame,
    olivine_dataframe: pd.DataFrame,
    *,
    rock_mg_column: str = "Mg#_rock",
    fo_column: str = "Fo",
    kd_values: tuple[float, ...] = (0.27, 0.30, 0.33),
    figure_size: tuple[float, float] = (7.0, 5.2),
):
    with plt.rc_context({"font.family": "Arial", "font.size": 9}):
        fig, ax = plt.subplots(figsize=figure_size)
        x_line = np.linspace(0.35, 0.9, 250)
        for kd in kd_values:
            y_line = [rhodes_equilibrium_fo(value, kd) for value in x_line]
            ax.plot(x_line, y_line, lw=1.0, label=f"Kd={kd:.2f}")
        if rock_mg_column in rock_dataframe.columns and fo_column in olivine_dataframe.columns:
            for _, rock in rock_dataframe.iterrows():
                mgnum = pd.to_numeric(pd.Series([rock.get(rock_mg_column)]), errors="coerce").iloc[0]
                if pd.isna(mgnum):
                    continue
                values = pd.to_numeric(olivine_dataframe[fo_column], errors="coerce").dropna()
                if not values.empty:
                    ax.scatter(np.full(len(values), float(mgnum)), values, s=34, alpha=0.8, label=str(rock.get("Rock", "rock")))
        ax.set_xlabel("Whole-rock / melt proxy Mg#")
        ax.set_ylabel("Olivine Fo, mol.%")
        ax.set_title("Rhodes-style olivine–liquid equilibrium screening")
        ax.legend(frameon=False, fontsize=8)
        ax.grid(True, alpha=0.18)
        fig.tight_layout()
        return fig


def figure_bytes(fig, fmt: str = "png", dpi: int = 600) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format=fmt, dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()

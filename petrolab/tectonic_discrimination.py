from __future__ import annotations

from dataclasses import dataclass

import matplotlib.pyplot as plt
import pandas as pd

from petrolab.column_schema import describe_header
from petrolab.plotting import _resolve_style


@dataclass(frozen=True)
class TectonicPreset:
    preset_id: str
    title: str
    x_label: str
    y_label: str
    xlim: tuple[float, float]
    ylim: tuple[float, float]
    boundaries: tuple[tuple[str, tuple[float, float], tuple[float, float], str], ...]
    labels: tuple[tuple[str, float, float], ...]
    source: str
    doi: str
    note: str


PEARCE_1984_SOURCE = "Pearce, Harris & Tindle (1984), Journal of Petrology 25, 956–983"
PEARCE_1984_DOI = "10.1093/petrology/25.4.956"


TECTONIC_PRESETS: dict[str, TectonicPreset] = {
    "pearce_y_nb": TectonicPreset(
        preset_id="pearce_y_nb",
        title="Y–Nb · granitoids · Pearce et al. (1984)",
        x_label="Y, µg/g",
        y_label="Nb, µg/g",
        xlim=(1.0, 2000.0),
        ylim=(0.8, 2500.0),
        boundaries=(
            ("VAG/WPG", (1.0, 2000.0), (50.0, 10.0), "solid"),
            ("VAG/ORG", (40.0, 1.0), (50.0, 10.0), "solid"),
            ("ORG/WPG", (50.0, 10.0), (1000.0, 100.0), "solid"),
            ("ORG(anom.)/WPG", (25.0, 25.0), (1000.0, 400.0), "dash"),
        ),
        labels=(
            ("VAG + syn-COLG", 8.0, 25.0),
            ("ORG", 180.0, 4.0),
            ("WPG", 250.0, 180.0),
        ),
        source=PEARCE_1984_SOURCE,
        doi=PEARCE_1984_DOI,
        note="Boundary coordinates are transcribed from the Fig. 3 caption. Post-collision and supra-subduction settings require geological context.",
    ),
    "pearce_rb_ynb": TectonicPreset(
        preset_id="pearce_rb_ynb",
        title="Rb–(Y+Nb) · granitoids · Pearce et al. (1984)",
        x_label="Y + Nb, µg/g",
        y_label="Rb, µg/g",
        xlim=(1.0, 2500.0),
        ylim=(0.8, 2500.0),
        boundaries=(
            ("syn-COLG/VAG", (2.0, 80.0), (55.0, 300.0), "solid"),
            ("syn-COLG/WPG", (55.0, 300.0), (400.0, 2000.0), "solid"),
            ("VAG/WPG", (55.0, 300.0), (51.5, 8.0), "solid"),
            ("VAG/ORG", (51.5, 8.0), (50.0, 1.0), "solid"),
            ("ORG/WPG", (51.5, 8.0), (2000.0, 400.0), "solid"),
        ),
        labels=(
            ("syn-COLG", 9.0, 450.0),
            ("VAG", 12.0, 30.0),
            ("ORG", 140.0, 4.0),
            ("WPG", 400.0, 500.0),
        ),
        source=PEARCE_1984_SOURCE,
        doi=PEARCE_1984_DOI,
        note="Boundary coordinates are transcribed from the Fig. 4 caption. Use for appropriate granitoid compositions together with geological constraints.",
    ),
}


def _element_column(dataframe: pd.DataFrame, element: str) -> str | None:
    """Resolve only an explicit concentration column; bare unknown-unit elements are unsafe."""
    wanted = str(element).casefold()
    for column in dataframe.columns:
        descriptor = describe_header(column)
        if descriptor.quantity_kind not in {"trace_element", "element_concentration"}:
            continue
        canonical = str(descriptor.canonical_name)
        base = canonical.split(" [", 1)[0].strip().casefold()
        if base == wanted and descriptor.canonical_unit:
            return str(column)
    return None


def prepare_tectonic_dataframe(dataframe: pd.DataFrame, preset_id: str) -> pd.DataFrame:
    if preset_id not in TECTONIC_PRESETS:
        raise ValueError("Неизвестный tectonic preset")
    work = dataframe.copy()
    y_col = _element_column(work, "Y")
    nb_col = _element_column(work, "Nb")
    if y_col is None or nb_col is None:
        raise ValueError("Для диаграммы нужны Y и Nb с явно распознанными concentration units (например µg/g или ppm)")
    y = pd.to_numeric(work[y_col], errors="coerce")
    nb = pd.to_numeric(work[nb_col], errors="coerce")
    if preset_id == "pearce_y_nb":
        work["_tectonic_x"] = y
        work["_tectonic_y"] = nb
    elif preset_id == "pearce_rb_ynb":
        rb_col = _element_column(work, "Rb")
        if rb_col is None:
            raise ValueError("Для Rb–(Y+Nb) нужны Rb, Y и Nb с явно распознанными concentration units")
        rb = pd.to_numeric(work[rb_col], errors="coerce")
        work["_tectonic_x"] = y + nb
        work["_tectonic_y"] = rb
    work = work.dropna(subset=["_tectonic_x", "_tectonic_y"])
    work = work[(work["_tectonic_x"] > 0) & (work["_tectonic_y"] > 0)]
    return work


def build_tectonic_figure(
    dataframe: pd.DataFrame,
    preset_id: str,
    *,
    group_column: str | None = None,
    style_map: dict | None = None,
    marker_size: float = 52.0,
    font_family: str = "Arial",
    font_size: float = 9.0,
    tick_size: float = 8.0,
    spine_width: float = 0.9,
    show_legend: bool = True,
    show_field_labels: bool = True,
    figure_size: tuple[float, float] = (7.2, 5.4),
):
    preset = TECTONIC_PRESETS[preset_id]
    work = prepare_tectonic_dataframe(dataframe, preset_id)
    with plt.rc_context({
        "font.family": font_family,
        "font.size": font_size,
        "xtick.labelsize": tick_size,
        "ytick.labelsize": tick_size,
    }):
        fig, ax = plt.subplots(figsize=figure_size, constrained_layout=True)
        for _, start, end, style in preset.boundaries:
            ax.plot(
                [start[0], end[0]], [start[1], end[1]],
                color="black", linewidth=1.0,
                linestyle="--" if style == "dash" else "-", zorder=1,
            )
        if show_field_labels:
            for text, x, y in preset.labels:
                ax.text(x, y, text, ha="center", va="center", fontsize=max(6.5, font_size - 0.5), zorder=2)

        if group_column and group_column in work.columns:
            groups = work[group_column].astype("string").fillna("Без группы").replace("", "Без группы")
            for index, name in enumerate(groups.unique().tolist()):
                part = work.loc[groups == name]
                stl = _resolve_style(name, index, style_map, monochrome=False)
                ax.scatter(
                    part["_tectonic_x"], part["_tectonic_y"],
                    s=float(marker_size) * stl["size_multiplier"],
                    marker=stl["marker"], alpha=stl["alpha"],
                    edgecolors=stl["edgecolors"], facecolors=stl["facecolors"],
                    linewidths=stl["outline_width"], label=str(name), zorder=4,
                )
            if show_legend:
                ax.legend(frameon=False)
        else:
            ax.scatter(work["_tectonic_x"], work["_tectonic_y"], s=float(marker_size), alpha=0.9, edgecolors="black", linewidths=0.6, zorder=4)

        ax.set_xscale("log")
        ax.set_yscale("log")
        ax.set_xlim(*preset.xlim)
        ax.set_ylim(*preset.ylim)
        ax.set_xlabel(preset.x_label)
        ax.set_ylabel(preset.y_label)
        ax.set_title(preset.title)
        ax.tick_params(direction="out", width=float(spine_width))
        for spine in ax.spines.values():
            spine.set_linewidth(float(spine_width))
        return fig

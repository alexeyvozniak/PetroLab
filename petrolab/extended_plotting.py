from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from typing import Iterable, Mapping

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


REE_ORDER = ("La", "Ce", "Pr", "Nd", "Sm", "Eu", "Gd", "Tb", "Dy", "Ho", "Er", "Tm", "Yb", "Lu")
SPIDER_ORDER = (
    "Cs", "Rb", "Ba", "Th", "U", "Nb", "Ta", "K", "La", "Ce", "Pb", "Pr",
    "Sr", "P", "Nd", "Zr", "Hf", "Sm", "Eu", "Ti", "Gd", "Tb", "Dy", "Y",
    "Ho", "Er", "Tm", "Yb", "Lu",
)

# McDonough & Sun (1995), Chemical Geology 120, 223–253.
CI_CHONDRITE_1995 = {
    "La": 0.237, "Ce": 0.613, "Pr": 0.0928, "Nd": 0.457, "Sm": 0.148,
    "Eu": 0.0563, "Gd": 0.199, "Tb": 0.0361, "Dy": 0.246, "Ho": 0.0546,
    "Er": 0.160, "Tm": 0.0247, "Yb": 0.161, "Lu": 0.0246,
}

# Sun & McDonough (1989), Geological Society Special Publication 42, 313–345.
PRIMITIVE_MANTLE_1989 = {
    "Rb": 0.635, "Ba": 6.989, "Th": 0.085, "U": 0.021, "Nb": 0.713,
    "Ta": 0.041, "K": 250.0, "La": 0.687, "Ce": 1.775, "Pb": 0.185,
    "Pr": 0.276, "Sr": 21.1, "P": 95.0, "Nd": 1.354, "Zr": 11.2,
    "Hf": 0.309, "Sm": 0.444, "Eu": 0.168, "Ti": 1300.0, "Gd": 0.596,
    "Tb": 0.108, "Dy": 0.737, "Y": 4.55, "Ho": 0.164, "Er": 0.480,
    "Tm": 0.074, "Yb": 0.493, "Lu": 0.074,
}

NORMALIZATION_REFERENCES = {
    "Без нормировки": None,
    "CI-хондрит · McDonough & Sun (1995)": CI_CHONDRITE_1995,
    "Primitive mantle · Sun & McDonough (1989)": PRIMITIVE_MANTLE_1989,
}


@dataclass(frozen=True)
class PatternResult:
    data: pd.DataFrame
    elements: tuple[str, ...]
    excluded_rows: int
    missing_elements: tuple[str, ...]


def _numeric(dataframe: pd.DataFrame, column: str) -> pd.Series:
    if column not in dataframe.columns:
        return pd.Series(np.nan, index=dataframe.index, dtype=float)
    return pd.to_numeric(dataframe[column], errors="coerce")


def available_elements(dataframe: pd.DataFrame, preferred: Iterable[str]) -> list[str]:
    return [element for element in preferred if element in dataframe.columns and _numeric(dataframe, element).notna().any()]


def prepare_pattern(
    dataframe: pd.DataFrame,
    elements: Iterable[str],
    reference: Mapping[str, float] | None = None,
) -> PatternResult:
    elements = tuple(elements)
    missing = tuple(element for element in elements if element not in dataframe.columns)
    usable = tuple(element for element in elements if element in dataframe.columns)
    if not usable:
        return PatternResult(pd.DataFrame(index=dataframe.index), (), len(dataframe), missing)

    out = pd.DataFrame(index=dataframe.index)
    for element in usable:
        values = _numeric(dataframe, element)
        if reference is not None:
            divisor = float(reference.get(element, np.nan))
            values = values / divisor if np.isfinite(divisor) and divisor > 0 else np.nan
        out[element] = values
    valid = out.notna().any(axis=1)
    return PatternResult(out.loc[valid].copy(), usable, int((~valid).sum()), missing)


def build_pattern_figure(
    pattern: PatternResult,
    *,
    labels: pd.Series | None = None,
    group: pd.Series | None = None,
    title: str = "",
    ylabel: str = "Concentration",
    log_y: bool = True,
    show_legend: bool = True,
    linewidth: float = 1.0,
    alpha: float = 0.75,
    figure_size: tuple[float, float] = (8.0, 5.2),
):
    fig, ax = plt.subplots(figsize=figure_size)
    x = np.arange(len(pattern.elements))
    if pattern.data.empty:
        ax.text(0.5, 0.5, "Нет подходящих данных", ha="center", va="center", transform=ax.transAxes)
    else:
        group_series = group.reindex(pattern.data.index).astype(str) if group is not None else None
        for idx, row in pattern.data.iterrows():
            label = str(labels.get(idx, idx)) if labels is not None else str(idx)
            if group_series is not None:
                label = str(group_series.get(idx, ""))
            ax.plot(x, row[list(pattern.elements)].to_numpy(dtype=float), marker="o", ms=3.5,
                    lw=linewidth, alpha=alpha, label=label)
    ax.set_xticks(x, pattern.elements, rotation=0)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if log_y:
        ax.set_yscale("log")
    ax.grid(True, axis="y", alpha=0.22)
    if show_legend and not pattern.data.empty and len(pattern.data) <= 30:
        handles, labels_ = ax.get_legend_handles_labels()
        unique: dict[str, object] = {}
        for handle, label in zip(handles, labels_):
            unique.setdefault(label, handle)
        ax.legend(unique.values(), unique.keys(), frameon=False, fontsize=8, loc="best")
    fig.tight_layout()
    return fig


def build_histogram_figure(
    dataframe: pd.DataFrame,
    column: str,
    *,
    bins: int = 20,
    group_column: str | None = None,
    density: bool = False,
    figure_size: tuple[float, float] = (7.0, 4.8),
):
    fig, ax = plt.subplots(figsize=figure_size)
    values = _numeric(dataframe, column)
    if group_column and group_column in dataframe.columns:
        for group_name, subset in dataframe.assign(_value=values).groupby(group_column, dropna=False):
            sample = pd.to_numeric(subset["_value"], errors="coerce").dropna()
            if not sample.empty:
                ax.hist(sample, bins=bins, alpha=0.55, density=density, label=str(group_name))
        ax.legend(frameon=False, fontsize=8)
    else:
        sample = values.dropna()
        if not sample.empty:
            ax.hist(sample, bins=bins, density=density, alpha=0.8)
    ax.set_xlabel(column)
    ax.set_ylabel("Плотность" if density else "Количество")
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return fig


def build_boxplot_figure(
    dataframe: pd.DataFrame,
    value_columns: list[str],
    *,
    group_column: str | None = None,
    show_fliers: bool = True,
    figure_size: tuple[float, float] = (8.0, 5.0),
):
    fig, ax = plt.subplots(figsize=figure_size)
    if group_column and group_column in dataframe.columns and len(value_columns) == 1:
        value = value_columns[0]
        groups: list[np.ndarray] = []
        names: list[str] = []
        for group_name, subset in dataframe.groupby(group_column, dropna=False):
            arr = _numeric(subset, value).dropna().to_numpy(dtype=float)
            if arr.size:
                groups.append(arr)
                names.append(str(group_name))
        if groups:
            ax.boxplot(groups, labels=names, showfliers=show_fliers)
            ax.set_ylabel(value)
    else:
        arrays = [_numeric(dataframe, column).dropna().to_numpy(dtype=float) for column in value_columns]
        good = [(column, array) for column, array in zip(value_columns, arrays) if array.size]
        if good:
            ax.boxplot([array for _, array in good], labels=[column for column, _ in good], showfliers=show_fliers)
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    return fig


def figure_bytes(fig, fmt: str = "png", dpi: int = 600) -> bytes:
    buffer = BytesIO()
    fig.savefig(buffer, format=fmt, dpi=dpi, bbox_inches="tight")
    return buffer.getvalue()

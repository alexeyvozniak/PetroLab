from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import matplotlib.axes
import numpy as np
import pandas as pd


@dataclass(frozen=True)
class XYOverlay:
    overlay_id: str
    title: str
    source: str
    doi: str
    note: str
    draw: Callable[[matplotlib.axes.Axes], None]
    classify: Callable[[pd.DataFrame], pd.Series] | None = None


def _wyatt_reference_y(mgo: np.ndarray) -> np.ndarray:
    x = np.asarray(mgo, dtype=float)
    low = -51.9078 + 52.8316 * x - 11.5519 * x**2 + 1.2003 * x**3 - 0.0475 * x**4
    high = 28.5188 + 4.7521 * x - 0.287 * x**2 + 0.0067 * x**3
    return np.where(x < 8.0, low, high)


def _draw_wyatt(ax: matplotlib.axes.Axes) -> None:
    x = np.linspace(4.0, 15.0, 400)
    y = _wyatt_reference_y(x)
    ax.plot(x, y, linestyle="--", linewidth=1.2, label="Wyatt et al. kimberlitic reference line")


def _classify_wyatt(dataframe: pd.DataFrame) -> pd.Series:
    mg = pd.to_numeric(dataframe.get("MgO"), errors="coerce")
    ti = pd.to_numeric(dataframe.get("TiO2"), errors="coerce")
    boundary = pd.Series(_wyatt_reference_y(mg.to_numpy(dtype=float)), index=dataframe.index)
    valid = mg.between(4.0, 15.0) & ti.notna()
    result = pd.Series("outside calibrated MgO range", index=dataframe.index, dtype="string")
    # Wyatt et al. describe the MgO-rich side of the bounding arc as kimberlitic.
    # With MgO on x and TiO2 on y, that relationship is represented by points on
    # the appropriate side of the reference arc; the line is primarily a screening aid.
    result.loc[valid & (ti >= boundary)] = "reference-line side A"
    result.loc[valid & (ti < boundary)] = "reference-line side B"
    return result


def _ca_int(cao: pd.Series, cr: pd.Series) -> pd.Series:
    condition = cao <= (3.375 + 0.25 * cr)
    return pd.Series(np.where(condition, 13.5 * cao / (cr + 13.5), cao - 0.25 * cr), index=cao.index)


def classify_grutter_g10(dataframe: pd.DataFrame) -> pd.Series:
    cao = pd.to_numeric(dataframe.get("CaO"), errors="coerce")
    cr = pd.to_numeric(dataframe.get("Cr2O3"), errors="coerce")
    mno = pd.to_numeric(dataframe.get("MnO"), errors="coerce") if "MnO" in dataframe else pd.Series(np.nan, index=dataframe.index)
    mg = pd.to_numeric(dataframe.get("MgO"), errors="coerce")
    fe = pd.to_numeric(dataframe.get("FeOt"), errors="coerce") if "FeOt" in dataframe else pd.to_numeric(dataframe.get("FeO"), errors="coerce")
    mgnum = (mg / 40.304) / ((mg / 40.304) + (fe / 71.844))
    ca_int = _ca_int(cao, cr)
    g10 = cr.ge(1.0) & cr.lt(22.0) & ca_int.ge(0.0) & ca_int.lt(3.375) & mgnum.between(0.75, 0.95)
    above = cr >= (5.0 + 0.94 * cao)
    result = pd.Series("not G10 diagnostic", index=dataframe.index, dtype="string")
    result.loc[g10 & above] = "G10A diagnostic"
    result.loc[g10 & ~above & mno.le(0.37)] = "G10A diagnostic"
    result.loc[g10 & ~above & mno.gt(0.37)] = "G10B diagnostic"
    return result


def _draw_grutter(ax: matplotlib.axes.Axes) -> None:
    cr = np.linspace(0.0, 12.0, 240)
    # CA_INT = 3.375 lower-Cr branch solved for CaO.
    ca_g10 = 0.25 * cr + 3.375
    ax.plot(ca_g10, cr, linestyle="--", linewidth=1.1, label="CA_INT = 3.375")
    ca = np.linspace(0.0, 8.0, 240)
    cr_ab = 5.0 + 0.94 * ca
    ax.plot(ca, cr_ab, linestyle=":", linewidth=1.1, label="G10A/B Cr boundary")


XY_OVERLAYS: dict[str, XYOverlay] = {
    "ilmenite_wyatt_kimberlite_curve": XYOverlay(
        overlay_id="ilmenite_wyatt_kimberlite_curve",
        title="Kimberlitic ilmenite reference line",
        source="Wyatt et al. (2004), Lithos 77, 819–840",
        doi="10.1016/j.lithos.2004.04.025",
        note=(
            "Bounding reference curve calibrated mainly for 4–15 wt.% MgO. The authors stress "
            "that related-rock ilmenites, including ultramafic lamprophyres, can cross the line; "
            "use population trends and Cr2O3 together with this screening aid."
        ),
        draw=_draw_wyatt,
        classify=None,
    ),
    "garnet_grutter_g10_diagnostic": XYOverlay(
        overlay_id="garnet_grutter_g10_diagnostic",
        title="G10 mantle-garnet diagnostic",
        source="Grütter et al. (2004), Lithos 77, 841–857; Grütter et al. 8IKC classification notes",
        doi="10.1016/j.lithos.2004.04.012",
        note=(
            "The displayed boundaries support G10 screening only. Formal G0–G12 assignment is a "
            "sequential multivariate classification and is not reduced to the CaO–Cr2O3 panel."
        ),
        draw=_draw_grutter,
        classify=classify_grutter_g10,
    ),
}


def draw_xy_overlay(ax: matplotlib.axes.Axes, overlay_id: str | None) -> XYOverlay | None:
    if not overlay_id:
        return None
    overlay = XY_OVERLAYS.get(overlay_id)
    if overlay is not None:
        overlay.draw(ax)
    return overlay

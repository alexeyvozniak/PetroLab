from __future__ import annotations

import numpy as np
import pandas as pd


HAWTHORNE_2012 = (
    "Hawthorne et al. (2012), American Mineralogist 97, 2031–2048, "
    "doi:10.2138/am.2012.4276"
)
LOCOCK_2014 = (
    "Locock (2014), Computers & Geosciences 62, 1–11, "
    "doi:10.1016/j.cageo.2013.09.011"
)


def _value(row: pd.Series, element: str) -> float:
    value = row.get(f"apfu_{element}", 0.0)
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if np.isfinite(number) and number > 0.0 else 0.0


def _move(source: dict[str, float], element: str, target: dict[str, float], capacity: float) -> None:
    room = max(float(capacity) - sum(target.values()), 0.0)
    amount = min(source.get(element, 0.0), room)
    if amount <= 0.0:
        return
    target[element] = target.get(element, 0.0) + amount
    source[element] = max(source.get(element, 0.0) - amount, 0.0)


def _b_subgroup(b: dict[str, float]) -> tuple[str, str]:
    """Return a conservative Hawthorne-2012 B-site subgroup screen.

    The 0.75/0.25 dominance boundaries are applied only after a near-complete
    two-cation B site has been allocated. Li-rich groups are deliberately not
    promoted to a routine name by this screening implementation.
    """
    total = sum(b.values())
    if total <= 0.0:
        return "unclassified", "B site is empty"
    if abs(total - 2.0) > 0.20:
        return "unclassified", f"B={total:.2f}, expected about 2"

    ca = b.get("Ca", 0.0)
    na = b.get("Na", 0.0)
    li = b.get("Li", 0.0)
    m2 = sum(b.get(element, 0.0) for element in ("Mg", "Fe2", "Mn"))
    ca_m2 = (ca + m2) / total
    na_li = (na + li) / total

    if ca_m2 >= 0.75:
        return ("calcium", "") if ca >= m2 else ("magnesium-iron-manganese", "")
    if 0.25 < ca_m2 < 0.75 and 0.25 < na_li < 0.75 and ca >= m2 and na >= li:
        return "sodium-calcium", ""
    if na_li >= 0.75 and na >= li:
        return "sodium", ""
    if na_li >= 0.75 and li > na:
        return "lithium-bearing", "Li-dominant B site requires a dedicated validated classifier"
    return "other/unsupported", "B-site dominance falls outside the routine Ca / Na-Ca / Na screen"


def _nearest_charge(value: float, maximum: int) -> tuple[int, float]:
    nodes = range(maximum + 1)
    chosen = min(nodes, key=lambda node: abs(float(value) - node))
    return chosen, abs(float(value) - chosen)


def _root_charge_candidate(subgroup: str, a_plus: float, c_plus: float, c_ti: float) -> str:
    """Return a root *charge-field* candidate, never a formal species name."""
    a_node, a_delta = _nearest_charge(a_plus, 2)
    c_node, c_delta = _nearest_charge(c_plus, 3)
    if a_delta > 0.50 or c_delta > 0.50:
        return ""

    if subgroup == "calcium" and a_node == 1 and c_ti > 0.50 and c_node >= 2:
        return "high-Ti kaersutite-related charge field"

    maps: dict[str, dict[tuple[int, int], str]] = {
        "calcium": {
            (0, 0): "tremolite–actinolite root charge field",
            (0, 1): "hornblende root charge field",
            (0, 2): "tschermakite root charge field",
            (1, 0): "edenite root charge field",
            (1, 1): "pargasite root charge field",
            (1, 2): "sadanagaite root charge field",
            (2, 1): "cannilloite root charge field",
        },
        "sodium-calcium": {
            (0, 1): "winchite root charge field",
            (0, 2): "barroisite root charge field",
            (1, 0): "richterite root charge field",
            (1, 1): "katophorite root charge field",
            (1, 2): "taramite root charge field",
        },
        "sodium": {
            (0, 2): "glaucophane/riebeckite charge field",
            (1, 1): "eckermannite/arfvedsonite/leakeite charge field",
            (1, 2): "nybøite root charge field",
        },
    }
    return maps.get(subgroup, {}).get((a_node, c_node), "")


def _has_explicit_fe3(row: pd.Series) -> bool:
    if "Fe2O3" not in row.index:
        return False
    try:
        raw = float(row.get("Fe2O3"))
    except (TypeError, ValueError):
        return False
    return np.isfinite(raw)


def _has_measured_halogen(row: pd.Series, column: str) -> bool:
    if column not in row.index:
        return False
    try:
        value = float(row.get(column))
    except (TypeError, ValueError):
        return False
    return np.isfinite(value)


def _allocate_one(row: pd.Series) -> dict[str, float | str]:
    elements = ("Si", "Al", "Ti", "Cr", "Fe3", "Mg", "Fe2", "Mn", "Ca", "Na", "K", "Li")
    remaining = {element: _value(row, element) for element in elements}
    t: dict[str, float] = {}
    c: dict[str, float] = {}
    b: dict[str, float] = {}
    a: dict[str, float] = {}

    for element in ("Si", "Al", "Ti"):
        _move(remaining, element, t, 8.0)
    for element in ("Al", "Ti", "Cr", "Fe3", "Mg", "Fe2", "Mn"):
        _move(remaining, element, c, 5.0)
    for element in ("Ca", "Na", "Mg", "Fe2", "Mn", "Li"):
        _move(remaining, element, b, 2.0)
    for element in ("Na", "K", "Ca", "Li"):
        amount = remaining.get(element, 0.0)
        if amount > 0.0:
            a[element] = a.get(element, 0.0) + amount
            remaining[element] = 0.0

    t_sum, c_sum, b_sum, a_sum = (sum(site.values()) for site in (t, c, b, a))
    subgroup, subgroup_note = _b_subgroup(b)
    a_plus = a.get("Na", 0.0) + a.get("K", 0.0) + 2.0 * a.get("Ca", 0.0)
    c_plus = c.get("Al", 0.0) + c.get("Fe3", 0.0) + 2.0 * c.get("Ti", 0.0)
    root_candidate = _root_charge_candidate(subgroup, a_plus, c_plus, c.get("Ti", 0.0))

    qc: list[str] = []
    if abs(t_sum - 8.0) > 0.15:
        qc.append(f"T={t_sum:.2f}, expected 8")
    if abs(c_sum - 5.0) > 0.20:
        qc.append(f"C={c_sum:.2f}, expected 5")
    if abs(b_sum - 2.0) > 0.20:
        qc.append(f"B={b_sum:.2f}, expected 2")
    if a_sum > 1.15:
        qc.append(f"A={a_sum:.2f} > 1")
    unsupported = sum(remaining.values())
    if unsupported > 0.05:
        qc.append("unallocated cations remain")
    li_present = _value(row, "Li") > 0.05
    if li_present:
        qc.append("Li-bearing composition requires dedicated Li site treatment")

    explicit_fe3 = _has_explicit_fe3(row)
    site_ok = not qc
    accepted_root = root_candidate if site_ok and explicit_fe3 and not li_present else ""
    notes = [item for item in (subgroup_note,) if item]
    if root_candidate and not explicit_fe3:
        notes.append("root charge field withheld because Fe3+ was not independently supplied")
    if not root_candidate:
        notes.append("routine root charge field unresolved")

    measured_f = _has_measured_halogen(row, "F")
    measured_cl = _has_measured_halogen(row, "Cl")
    c_ti = c.get("Ti", 0.0)
    w_o_ti_proxy = min(2.0 * c_ti, 2.0)
    if measured_f and measured_cl:
        w_status = "F and Cl measured; OH/O2− still not independently constrained"
    else:
        w_status = "W site unresolved: F/Cl incomplete and H/O not independently constrained"
    if c_ti >= 0.30:
        w_status += f"; Ti-based O2− screening proxy={w_o_ti_proxy:.2f} apfu"

    output: dict[str, float | str] = {
        "amp_T_sum": t_sum,
        "amp_C_sum": c_sum,
        "amp_B_sum": b_sum,
        "amp_A_sum": a_sum,
        "amp_A_vacancy": max(1.0 - a_sum, 0.0),
        "amp_A_plus": a_plus,
        "amp_C_plus": c_plus,
        "amp_B_subgroup": subgroup,
        "amp_root_charge_candidate": root_candidate,
        "amp_root_field": accepted_root,
        # Store provenance as 1.0/0.0 rather than bool so invalid formula rows can
        # be masked with NaN without forcing a lossy dtype conversion in pandas.
        "amp_Fe3_explicit": 1.0 if explicit_fe3 else 0.0,
        "amp_W_O_Ti_proxy": w_o_ti_proxy,
        "amp_W_status": w_status,
        "amp_site_QC": "норма" if site_ok else "; ".join(qc),
        "amp_classification_note": "; ".join(notes),
    }
    for site_name, site in (("T", t), ("C", c), ("B", b), ("A", a)):
        for element, value in site.items():
            output[f"amp_{site_name}_{element}"] = value
    return output


def attach_amphibole_ima_diagnostics(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Attach conservative IMA-2012 site/subgroup diagnostics.

    This routine is deliberately a screening layer. It does not assign a formal
    amphibole species because routine EPMA commonly leaves Fe3+/Fe2+ and the W
    anion budget underconstrained. The root charge field is exposed only when
    Fe3+ was explicitly supplied and the simplified site allocation passes QC.
    """
    result = dataframe.copy()
    if result.empty:
        return result
    diagnostics = pd.DataFrame([_allocate_one(row) for _, row in result.iterrows()], index=result.index)
    for column in diagnostics.columns:
        result[column] = diagnostics[column]
    return result

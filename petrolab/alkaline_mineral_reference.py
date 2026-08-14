from __future__ import annotations

from dataclasses import dataclass


ALKALINE_REFERENCE_VERSION = "2026.08.1"


@dataclass(frozen=True)
class AlkalineMineralReference:
    name: str
    family: str
    chemical_target: str
    ideal_formula: str = ""
    epma_resolution: str = "group"
    note: str = ""


ALKALINE_MINERALS: tuple[AlkalineMineralReference, ...] = (
    # Nb-Ta-Ti oxides and related alkaline accessory phases
    AlkalineMineralReference("pyrochlore-supergroup", "Nb-Ta oxide", "pyrochlore-supergroup", note="Exact supergroup member requires site/anion chemistry; broad target only."),
    AlkalineMineralReference("fluorcalciopyrochlore", "Nb-Ta oxide", "pyrochlore-supergroup", note="Species-level call requires full supergroup nomenclature calculation."),
    AlkalineMineralReference("hydroxycalciopyrochlore", "Nb-Ta oxide", "pyrochlore-supergroup", note="OH cannot be resolved directly by routine EPMA."),
    AlkalineMineralReference("oxycalciopyrochlore", "Nb-Ta oxide", "pyrochlore-supergroup"),
    AlkalineMineralReference("microlite-supergroup", "Nb-Ta oxide", "pyrochlore-supergroup", note="Ta-rich members require full B-site/site-occupancy calculation."),
    AlkalineMineralReference("loparite-(Ce)", "perovskite-related", "REE-Na titanate (loparite-type)", "(Na,Ce,Ca)(Ti,Nb)O3", note="Broad chemical target; exact perovskite-supergroup member requires formula calculation."),

    # Melilite and Ca-rich silicates
    AlkalineMineralReference("akermanite", "melilite", "melilite-group", "Ca2MgSi2O7"),
    AlkalineMineralReference("gehlenite", "melilite", "melilite-group", "Ca2Al2SiO7"),
    AlkalineMineralReference("soda-melilite", "melilite", "melilite-group", note="Na-rich melilite component; use group-level result unless formula calculation supports a member."),
    AlkalineMineralReference("wollastonite", "Ca silicate", "wollastonite-type Ca silicate", "CaSiO3"),
    AlkalineMineralReference("pectolite", "pyroxenoid", "pectolite-like Na-Ca pyroxenoid", "NaCa2Si3O8(OH)", note="H/OH is not determined by routine EPMA."),
    AlkalineMineralReference("xonotlite", "Ca silicate", "hydrous Ca-silicate", note="Hydration state requires external evidence."),
    AlkalineMineralReference("tobermorite", "Ca silicate", "hydrous Ca-silicate", note="Hydration state requires external evidence."),

    # Hydrogarnet and alteration assemblages
    AlkalineMineralReference("hydrogrossular", "garnet", "Ca-Al garnet / hydrogarnet-like", note="Hydrogarnet substitution requires OH/H information beyond routine EPMA."),
    AlkalineMineralReference("hibschite", "garnet", "Ca-Al garnet / hydrogarnet-like", note="Hydrogarnet-series member requires formula/OH constraints."),
    AlkalineMineralReference("katoite", "garnet", "Ca-Al garnet / hydrogarnet-like", "Ca3Al2(OH)12", note="H/OH cannot be measured directly by routine EPMA."),

    # Zeolite and late hydrothermal framework minerals
    AlkalineMineralReference("natrolite", "zeolite", "Na-Ca zeolite-like framework", "Na2Al2Si3O10·2H2O", note="Hydration cannot be resolved by routine EPMA."),
    AlkalineMineralReference("mesolite", "zeolite", "Na-Ca zeolite-like framework", note="Natrolite-group chemistry; H2O not measured."),
    AlkalineMineralReference("scolecite", "zeolite", "Na-Ca zeolite-like framework", note="Natrolite-group chemistry; H2O not measured."),
    AlkalineMineralReference("thomsonite", "zeolite", "Na-Ca zeolite-like framework", note="Group-level EPMA target."),
    AlkalineMineralReference("chabazite", "zeolite", "Na-Ca zeolite-like framework", note="Group-level EPMA target."),

    # Zr-Ti alkaline silicates
    AlkalineMineralReference("eudialyte-group", "Zr silicate", "eudialyte-group-like Na-Ca-Zr silicate", note="Complex site chemistry; broad recognition target only."),
    AlkalineMineralReference("eudialyte", "Zr silicate", "eudialyte-group-like Na-Ca-Zr silicate", note="Exact group-member assignment requires full structural formula."),
    AlkalineMineralReference("astrophyllite", "Ti silicate", "alkaline Ti-silicate (astrophyllite/lamprophyllite-like)", note="Broad EPMA target; end-member/site calculation required."),
    AlkalineMineralReference("lamprophyllite", "Ti silicate", "alkaline Ti-silicate (astrophyllite/lamprophyllite-like)", note="Broad EPMA target; end-member/site calculation required."),

    # Carbonatite accessory carbonates
    AlkalineMineralReference("Sr-rich calcite", "carbonate", "Sr-rich Ca carbonate", note="Compositional type, not an IMA species name."),
    AlkalineMineralReference("Ba-rich calcite", "carbonate", "Ba-rich Ca carbonate", note="Compositional type, not an IMA species name."),
)


def references_by_target() -> dict[str, tuple[AlkalineMineralReference, ...]]:
    grouped: dict[str, list[AlkalineMineralReference]] = {}
    for item in ALKALINE_MINERALS:
        grouped.setdefault(item.chemical_target, []).append(item)
    return {key: tuple(values) for key, values in grouped.items()}

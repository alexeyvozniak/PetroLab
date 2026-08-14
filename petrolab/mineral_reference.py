from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


MINERAL_REFERENCE_VERSION = "2026.08.1"
REFERENCE_NOTE = (
    "Mineral names and ideal formulae are intended as a recognition reference, not as a substitute "
    "for IMA species determination. Chemical targets deliberately collapse polymorphs and other "
    "species that cannot be distinguished reliably from routine EPMA chemistry alone."
)


@dataclass(frozen=True)
class MineralReference:
    name: str
    family: str
    chemical_target: str
    ideal_formula: str = ""
    epma_resolution: str = "species"
    note: str = ""


# Sources used to define names/formula concepts and conservative families:
# - IMA Database of Mineral Properties / RRUFF (mineral names and ideal chemistry)
# - standard IMA mineral-group nomenclature for pyroxenes, amphiboles, micas, feldspars and garnets.
# The classifier does NOT claim that every listed IMA species is uniquely resolvable by EPMA.
MINERALS: tuple[MineralReference, ...] = (
    # Olivine and related orthosilicates
    MineralReference("forsterite", "olivine", "olivine", "Mg2SiO4"),
    MineralReference("fayalite", "olivine", "olivine", "Fe2SiO4"),
    MineralReference("tephroite", "olivine", "olivine", "Mn2SiO4"),
    MineralReference("monticellite", "olivine", "monticellite", "CaMgSiO4"),
    MineralReference("kirschsteinite", "olivine", "monticellite", "CaFeSiO4"),

    # Pyroxenes
    MineralReference("enstatite", "pyroxene", "orthopyroxene", "Mg2Si2O6"),
    MineralReference("ferrosilite", "pyroxene", "orthopyroxene", "Fe2Si2O6"),
    MineralReference("pigeonite", "pyroxene", "low-Ca pyroxene", "(Mg,Fe,Ca)2Si2O6"),
    MineralReference("diopside", "pyroxene", "clinopyroxene", "CaMgSi2O6"),
    MineralReference("hedenbergite", "pyroxene", "clinopyroxene", "CaFeSi2O6"),
    MineralReference("augite", "pyroxene", "clinopyroxene", "(Ca,Na)(Mg,Fe,Al,Ti)(Si,Al)2O6"),
    MineralReference("jadeite", "pyroxene", "Na-clinopyroxene", "NaAlSi2O6"),
    MineralReference("aegirine", "pyroxene", "Na-clinopyroxene", "NaFe3+Si2O6"),
    MineralReference("omphacite", "pyroxene", "Na-Ca clinopyroxene", "(Ca,Na)(Mg,Fe2+,Al)Si2O6"),
    MineralReference("spodumene", "pyroxene", "Li-pyroxene", "LiAlSi2O6", note="Li is usually not measured by routine EPMA; species confirmation may need external evidence."),

    # Amphiboles; routine EPMA commonly supports group/subgroup assignment better than a unique species
    MineralReference("tremolite", "amphibole", "calcic amphibole", "Ca2Mg5Si8O22(OH)2"),
    MineralReference("actinolite", "amphibole", "calcic amphibole", "Ca2(Mg,Fe)5Si8O22(OH)2"),
    MineralReference("ferro-actinolite", "amphibole", "calcic amphibole", "Ca2Fe5Si8O22(OH)2"),
    MineralReference("magnesio-hornblende", "amphibole", "calcic amphibole", epma_resolution="group"),
    MineralReference("ferro-hornblende", "amphibole", "calcic amphibole", epma_resolution="group"),
    MineralReference("pargasite", "amphibole", "calcic amphibole", epma_resolution="group"),
    MineralReference("ferro-pargasite", "amphibole", "calcic amphibole", epma_resolution="group"),
    MineralReference("kaersutite", "amphibole", "Ti-rich calcic amphibole", epma_resolution="group"),
    MineralReference("riebeckite", "amphibole", "sodic amphibole", "Na2Fe3Fe2Si8O22(OH)2", epma_resolution="group"),
    MineralReference("arfvedsonite", "amphibole", "sodic amphibole", epma_resolution="group"),
    MineralReference("glaucophane", "amphibole", "sodic amphibole", "Na2Mg3Al2Si8O22(OH)2", epma_resolution="group"),
    MineralReference("winchite", "amphibole", "sodic-calcic amphibole", epma_resolution="group"),

    # Micas
    MineralReference("phlogopite", "mica", "trioctahedral mica", "KMg3AlSi3O10(OH)2"),
    MineralReference("annite", "mica", "trioctahedral mica", "KFe3AlSi3O10(OH)2"),
    MineralReference("biotite", "mica", "trioctahedral mica", epma_resolution="group", note="Biotite is treated as a compositional group label rather than a unique species."),
    MineralReference("muscovite", "mica", "dioctahedral mica", "KAl2(AlSi3O10)(OH)2"),
    MineralReference("celadonite", "mica", "dioctahedral mica", epma_resolution="group"),
    MineralReference("lepidolite", "mica", "Li-mica", epma_resolution="group", note="Li is not quantified by routine EPMA."),
    MineralReference("zinnwaldite", "mica", "Li-mica", epma_resolution="group", note="Li is not quantified by routine EPMA."),

    # Feldspars
    MineralReference("albite", "feldspar", "plagioclase", "NaAlSi3O8"),
    MineralReference("anorthite", "feldspar", "plagioclase", "CaAl2Si2O8"),
    MineralReference("orthoclase", "feldspar", "K-feldspar", "KAlSi3O8", "group", "K-feldspar polymorphs are not distinguished by chemistry alone."),
    MineralReference("sanidine", "feldspar", "K-feldspar", "KAlSi3O8", "group", "K-feldspar polymorphs are not distinguished by chemistry alone."),
    MineralReference("microcline", "feldspar", "K-feldspar", "KAlSi3O8", "group", "K-feldspar polymorphs are not distinguished by chemistry alone."),

    # Feldspathoids and related framework minerals
    MineralReference("nepheline", "feldspathoid", "nepheline", "(Na,K)AlSiO4"),
    MineralReference("kalsilite", "feldspathoid", "kalsilite", "KAlSiO4"),
    MineralReference("leucite", "feldspathoid", "leucite", "KAlSi2O6"),
    MineralReference("sodalite", "feldspathoid", "sodalite-group", "Na8(Al6Si6O24)Cl2", "group"),
    MineralReference("nosean", "feldspathoid", "sodalite-group", "Na8(Al6Si6O24)(SO4)", "group"),
    MineralReference("hauyne", "feldspathoid", "sodalite-group", "(Na,Ca)8(Al6Si6O24)(SO4,S)2", "group"),
    MineralReference("cancrinite", "feldspathoid", "cancrinite-group", "Na6Ca2(Al6Si6O24)(CO3)2", "group"),

    # Garnets
    MineralReference("pyrope", "garnet", "garnet", "Mg3Al2Si3O12"),
    MineralReference("almandine", "garnet", "garnet", "Fe3Al2Si3O12"),
    MineralReference("spessartine", "garnet", "garnet", "Mn3Al2Si3O12"),
    MineralReference("grossular", "garnet", "garnet", "Ca3Al2Si3O12"),
    MineralReference("andradite", "garnet", "garnet", "Ca3Fe2Si3O12"),
    MineralReference("uvarovite", "garnet", "garnet", "Ca3Cr2Si3O12"),
    MineralReference("schorlomite", "garnet", "Ti-rich garnet", epma_resolution="group"),

    # Oxides
    MineralReference("spinel", "spinel", "spinel-group oxide", "MgAl2O4", "group"),
    MineralReference("hercynite", "spinel", "spinel-group oxide", "FeAl2O4", "group"),
    MineralReference("chromite", "spinel", "Cr-spinel", "FeCr2O4", "group"),
    MineralReference("magnetite", "spinel", "Fe-oxide", "Fe3O4", "group"),
    MineralReference("ulvospinel", "spinel", "Fe-Ti oxide", "Fe2TiO4", "group"),
    MineralReference("ilmenite", "oxide", "Fe-Ti oxide", "FeTiO3"),
    MineralReference("hematite", "oxide", "Fe-oxide", "Fe2O3"),
    MineralReference("rutile", "oxide", "TiO2 phase", "TiO2", "group", "TiO2 polymorphs require structural evidence for species-level distinction."),
    MineralReference("anatase", "oxide", "TiO2 phase", "TiO2", "group", "TiO2 polymorphs require structural evidence for species-level distinction."),
    MineralReference("brookite", "oxide", "TiO2 phase", "TiO2", "group", "TiO2 polymorphs require structural evidence for species-level distinction."),
    MineralReference("baddeleyite", "oxide", "baddeleyite", "ZrO2"),
    MineralReference("perovskite", "oxide", "perovskite", "CaTiO3"),

    # Phosphates and common accessory minerals
    MineralReference("fluorapatite", "apatite", "apatite", "Ca5(PO4)3F", "group"),
    MineralReference("hydroxylapatite", "apatite", "apatite", "Ca5(PO4)3OH", "group"),
    MineralReference("chlorapatite", "apatite", "apatite", "Ca5(PO4)3Cl", "group"),
    MineralReference("monazite-(Ce)", "phosphate", "monazite", "CePO4", "group"),
    MineralReference("xenotime-(Y)", "phosphate", "xenotime", "YPO4", "group"),
    MineralReference("zircon", "accessory", "zircon", "ZrSiO4"),
    MineralReference("titanite", "accessory", "titanite", "CaTiSiO5"),
    MineralReference("allanite-(Ce)", "epidote", "REE-epidote", epma_resolution="group"),
    MineralReference("epidote", "epidote", "epidote-group", "Ca2Al2FeSi3O12(OH)", "group"),
    MineralReference("clinozoisite", "epidote", "epidote-group", "Ca2Al3Si3O12(OH)", "group"),
    MineralReference("zoisite", "epidote", "epidote-group", "Ca2Al3Si3O12(OH)", "group", "Zoisite/clinozoisite need structural evidence for robust polymorph distinction."),
    MineralReference("tourmaline", "tourmaline", "tourmaline-group", epma_resolution="group"),
    MineralReference("staurolite", "metamorphic", "staurolite", epma_resolution="group"),
    MineralReference("cordierite", "metamorphic", "cordierite", "Mg2Al4Si5O18"),
    MineralReference("sillimanite", "Al2SiO5", "Al2SiO5 phase", "Al2SiO5", "group", "Al2SiO5 polymorphs cannot be separated by EPMA chemistry alone."),
    MineralReference("kyanite", "Al2SiO5", "Al2SiO5 phase", "Al2SiO5", "group", "Al2SiO5 polymorphs cannot be separated by EPMA chemistry alone."),
    MineralReference("andalusite", "Al2SiO5", "Al2SiO5 phase", "Al2SiO5", "group", "Al2SiO5 polymorphs cannot be separated by EPMA chemistry alone."),
    MineralReference("quartz", "silica", "silica", "SiO2", "group", "Silica polymorphs require structural/context information."),

    # Carbonates: especially important for alkaline-carbonatite work
    MineralReference("calcite", "carbonate", "Ca-carbonate", "CaCO3"),
    MineralReference("aragonite", "carbonate", "Ca-carbonate", "CaCO3", "group", "Calcite/aragonite cannot be distinguished from cation chemistry alone."),
    MineralReference("dolomite", "carbonate", "Ca-Mg carbonate", "CaMg(CO3)2"),
    MineralReference("ankerite", "carbonate", "Ca-Fe-Mg carbonate", "Ca(Fe,Mg,Mn)(CO3)2"),
    MineralReference("magnesite", "carbonate", "Mg-carbonate", "MgCO3"),
    MineralReference("siderite", "carbonate", "Fe-carbonate", "FeCO3"),
    MineralReference("rhodochrosite", "carbonate", "Mn-carbonate", "MnCO3"),
    MineralReference("strontianite", "carbonate", "Sr-carbonate", "SrCO3"),
    MineralReference("bastnasite-(Ce)", "carbonate", "REE-fluorocarbonate", "CeCO3F", "group"),

    # Additional common accessory / alteration phases
    MineralReference("barite", "sulfate", "barite", "BaSO4"),
    MineralReference("celestine", "sulfate", "celestine", "SrSO4"),
    MineralReference("anhydrite", "sulfate", "Ca-sulfate", "CaSO4"),
    MineralReference("gypsum", "sulfate", "Ca-sulfate", "CaSO4·2H2O", "group", "Hydration state is not robustly resolved from routine EPMA."),
)


def catalog_payload() -> list[dict[str, str]]:
    return [
        {
            "name": item.name,
            "family": item.family,
            "chemical_target": item.chemical_target,
            "ideal_formula": item.ideal_formula,
            "epma_resolution": item.epma_resolution,
            "note": item.note,
        }
        for item in MINERALS
    ]


def catalog_hash() -> str:
    payload = json.dumps(catalog_payload(), sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def references_by_target() -> dict[str, tuple[MineralReference, ...]]:
    grouped: dict[str, list[MineralReference]] = {}
    for item in MINERALS:
        grouped.setdefault(item.chemical_target, []).append(item)
    return {key: tuple(value) for key, value in grouped.items()}

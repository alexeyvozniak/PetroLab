from __future__ import annotations

from petrolab.alkaline_mineral_reference import ALKALINE_MINERALS, ALKALINE_REFERENCE_VERSION, references_by_target

assert ALKALINE_REFERENCE_VERSION == "2026.08.1"
assert len(ALKALINE_MINERALS) >= 25
by_target = references_by_target()
for required in (
    "pyrochlore-supergroup",
    "REE-Na titanate (loparite-type)",
    "melilite-group",
    "pectolite-like Na-Ca pyroxenoid",
    "wollastonite-type Ca silicate",
    "Ca-Al garnet / hydrogarnet-like",
    "Na-Ca zeolite-like framework",
    "eudialyte-group-like Na-Ca-Zr silicate",
):
    assert required in by_target, required

print(f"alkaline mineral reference: OK; entries={len(ALKALINE_MINERALS)}")

from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="petrolab_germ_import_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

import pandas as pd

from petrolab.db import ensure_storage
from petrolab.partition_import import import_partition_table
from petrolab.partitioning import assess_model_context, list_partition_models

ensure_storage()
created = import_partition_table(pd.DataFrame([
    {
        "contribution_id": 265,
        "rock_types": "Syenite",
        "minerals": "Clinopyroxene",
        "element": "La",
        "kd": 0.06,
        "kd_sigma": None,
        "kd_low": 0.03,
        "kd_high": 0.66,
        "kd_definition": "Solid-Melt",
        "kd_types": "Phenocryst-Matrix",
    },
    {
        "contribution_id": 265,
        "rock_types": "Syenite",
        "minerals": "Clinopyroxene",
        "element": "Cs",
        "kd": None,
        "kd_sigma": None,
        "kd_low": 0.03,
        "kd_high": 0.05,
        "kd_definition": "Solid-Melt",
        "kd_types": "Phenocryst-Matrix",
    },
]))
assert len(created) == 1
model = list_partition_models()[0]
assert model["values"]["La"] == 0.06
assert model["values"]["Cs"] == {"low": 0.03, "high": 0.05}
assert model["source"]["database"] == "GERM KdD"
assert model["source"]["contribution_id"] == "265"
assert model["source"]["element_metadata"]["La"]["high"] == 0.66
assert model["applicability"]["kind"] == "Phenocryst-Matrix"
print("GERM partition import tests: OK")

assert assess_model_context(model, "Syenite")["status"] == "соответствует"
foreign = assess_model_context(model, "Lamprophyre")
assert foreign["status"] == "предупреждение"
assert "Syenite" in foreign["message"]
print("model-context visibility tests: OK")

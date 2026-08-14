from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="petrolab_germ_import_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

import pandas as pd

from petrolab.db import ensure_storage
from petrolab.partition_import import import_partition_table, read_partition_upload
from petrolab.partitioning import assess_model_context, list_partition_models

ensure_storage()
syenite_export = b"""tab delimited\tcontribution
data_model_version\tdescription
1.0\tDownloaded from KdD.
>>>>>>>>>>
tab delimited\tkds
rock_types\tminerals\telement\tkd\tkd_low\tkd_high\tkd_definition\tkd_types
Syenite\tClinopyroxene\tRb\t\t0.02\t0.04\tSolid-Melt\tPhenocryst-Matrix
"""
syenite_table = read_partition_upload(syenite_export, "syenite.txt")
assert syenite_table.attrs["germ_kdd_export"] is True
syenite_created = import_partition_table(syenite_table)
assert len(syenite_created) == 1
assert list_partition_models()[0]["source"]["database"] == "GERM KdD"
print("GERM export without contribution_id tests: OK")

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

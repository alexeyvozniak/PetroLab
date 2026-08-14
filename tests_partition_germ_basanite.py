from __future__ import annotations

import os
import tempfile
from pathlib import Path

_TMP = tempfile.TemporaryDirectory(prefix="petrolab_germ_basanite_")
os.environ["PETROLAB_DATA_DIR"] = str(Path(_TMP.name) / "data")

from petrolab.db import ensure_storage
from petrolab.partition_seed_germ import GERM_BASANITE_FILE, seed_germ_basanite_models
from petrolab.partitioning import list_partition_models

ensure_storage()
assert GERM_BASANITE_FILE.is_file()
created = seed_germ_basanite_models()
assert created
models = list_partition_models()
assert len(models) == len(created)
assert all(model["source"]["database"] == "GERM KdD" for model in models)
assert all(model["applicability"]["rock"] == "Basanite" for model in models)
assert any("low" in metadata or "high" in metadata
           for model in models
           for metadata in model["source"]["element_metadata"].values())
assert seed_germ_basanite_models() == []
print("Built-in GERM basanite library tests: OK")

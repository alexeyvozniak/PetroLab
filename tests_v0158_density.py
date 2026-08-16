from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def test_new_install_defaults_to_compact_density() -> None:
    with tempfile.TemporaryDirectory(prefix="petrolab_density_") as tmp:
        os.environ["PETROLAB_DATA_DIR"] = str(Path(tmp) / "data")
        from petrolab.settings_service import DEFAULT_SETTINGS, SETTINGS_PATH, load_settings

        assert DEFAULT_SETTINGS["ui_density"] == "compact"
        assert not SETTINGS_PATH.exists()
        assert load_settings()["ui_density"] == "compact"


def test_explicit_comfortable_preference_is_preserved() -> None:
    from petrolab.settings_service import SETTINGS_PATH, load_settings, save_settings

    save_settings({"ui_density": "comfortable"})
    assert SETTINGS_PATH.exists()
    raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    assert raw["ui_density"] == "comfortable"
    assert load_settings()["ui_density"] == "comfortable"


def main() -> None:
    test_new_install_defaults_to_compact_density()
    test_explicit_comfortable_preference_is_preserved()
    print("v0.15.8 compact density default: OK")


if __name__ == "__main__":
    main()

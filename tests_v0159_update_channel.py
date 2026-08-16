from __future__ import annotations

from pathlib import Path

from petrolab.update_checker import VERSION_SOURCE_URL


ROOT = Path(__file__).resolve().parent


def main() -> None:
    updater = (ROOT / "installer" / "update_petrolab.ps1").read_text(encoding="utf-8")
    assert "/windows-latest/petrolab/__init__.py" in VERSION_SOURCE_URL
    assert "/main/petrolab/__init__.py" not in VERSION_SOURCE_URL
    assert "git/ref/tags/windows-latest" in updater
    print("PetroLab update notice and updater share windows-latest: OK")


if __name__ == "__main__":
    main()

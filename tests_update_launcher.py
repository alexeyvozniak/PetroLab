from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
launcher = (ROOT / "UPDATE_PETROLAB.bat").read_bytes()
text = launcher.decode("ascii")

assert b"\n" not in launcher.replace(b"\r\n", b"")
for required in [
    "git fetch origin main --quiet",
    "git merge --ff-only origin/main",
    "git diff --ignore-space-at-eol --quiet",
    "petrolab-before-update-",
    "INSTALL_PETROLAB.bat",
    "START_PETROLAB.bat",
    "Your PetroLab data, Excel files and images will not be touched.",
]:
    assert required in text, required
for forbidden in ["git reset", "git clean", "git checkout", "--hard"]:
    assert forbidden not in text, forbidden

print("update launcher tests: OK")

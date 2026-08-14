"""Small, privacy-preserving check for a newer PetroLab program version."""
from __future__ import annotations

import re
from urllib.error import URLError
from urllib.request import Request, urlopen


VERSION_SOURCE_URL = (
    "https://raw.githubusercontent.com/alexeyvozniak/PetroLab/main/petrolab/__init__.py"
)
_VERSION_RE = re.compile(r'^__version__\s*=\s*["\'](\d+(?:\.\d+){1,3})["\']', re.MULTILINE)


def version_key(value: str) -> tuple[int, ...] | None:
    """Parse a simple PetroLab release version without accepting arbitrary text."""
    match = re.fullmatch(r"v?(\d+(?:\.\d+){1,3})", str(value).strip())
    if not match:
        return None
    return tuple(int(part) for part in match.group(1).split("."))


def is_newer(remote_version: str, installed_version: str) -> bool:
    remote, installed = version_key(remote_version), version_key(installed_version)
    if remote is None or installed is None:
        return False
    length = max(len(remote), len(installed))
    return remote + (0,) * (length - len(remote)) > installed + (0,) * (length - len(installed))


def fetch_remote_version(*, timeout: float = 1.2, opener=urlopen) -> str | None:
    """Fetch only the public version declaration; never send project or user data."""
    request = Request(VERSION_SOURCE_URL, headers={"User-Agent": "PetroLab-update-check"})
    try:
        with opener(request, timeout=float(timeout)) as response:
            source = response.read().decode("utf-8", errors="replace")
    except (OSError, URLError, TimeoutError, ValueError):
        return None
    match = _VERSION_RE.search(source)
    return match.group(1) if match else None


def available_update(installed_version: str, *, timeout: float = 1.2, opener=urlopen) -> str | None:
    remote = fetch_remote_version(timeout=timeout, opener=opener)
    return remote if remote and is_newer(remote, installed_version) else None

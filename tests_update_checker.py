from __future__ import annotations

from petrolab.update_checker import available_update, fetch_remote_version, is_newer, version_key


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def read(self) -> bytes:
        return self.payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def _opener(payload: bytes):
    def open_request(_request, timeout: float):
        assert timeout == 0.4
        return _Response(payload)
    return open_request


assert version_key("v0.12.2") == (0, 12, 2)
assert version_key("0.12") == (0, 12)
assert version_key("latest") is None
assert is_newer("0.12.2", "0.12.1")
assert not is_newer("0.12.1", "0.12.1")
assert not is_newer("bad", "0.12.1")

payload = b'__version__ = "0.12.3"\n'
assert fetch_remote_version(timeout=0.4, opener=_opener(payload)) == "0.12.3"
assert available_update("0.12.2", timeout=0.4, opener=_opener(payload)) == "0.12.3"
assert available_update("0.12.3", timeout=0.4, opener=_opener(payload)) is None


def _offline(_request, timeout: float):
    assert timeout == 0.4
    raise OSError("offline")


assert fetch_remote_version(timeout=0.4, opener=_offline) is None

print("update checker tests: OK")

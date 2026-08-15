from __future__ import annotations

from petrolab.ui.universal_intake import (
    _KIND_IMAGE,
    _KIND_SKIP,
    _KIND_TABLE,
    _file_token,
    _guessed_kind,
)


def test_universal_intake_classifies_supported_common_files():
    assert _guessed_kind("probe.xlsx") == _KIND_TABLE
    assert _guessed_kind("laser.csv") == _KIND_TABLE
    assert _guessed_kind("grain_BSE.tif") == _KIND_IMAGE
    assert _guessed_kind("sample.jpeg") == _KIND_IMAGE
    assert _guessed_kind("notes.txt") == _KIND_SKIP


def test_file_token_changes_with_content_not_only_filename():
    assert _file_token("a.png", b"one") != _file_token("a.png", b"two")
    assert _file_token("a.png", b"one") == _file_token("a.png", b"one")


if __name__ == "__main__":
    test_universal_intake_classifies_supported_common_files()
    test_file_token_changes_with_content_not_only_filename()
    print("v0.15.1 universal intake tests: OK")

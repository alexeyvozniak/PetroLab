from __future__ import annotations

from pathlib import Path

from petrolab.ui.pages.v0151_intake_wrappers import _project_session_token


def main() -> None:
    raw = "a1b2c3"
    assert _project_session_token(1, raw) == "p1_a1b2c3"
    assert _project_session_token(2, raw) == "p2_a1b2c3"
    assert _project_session_token(1, raw) != _project_session_token(2, raw)

    source = Path("petrolab/ui/pages/v0151_intake_wrappers.py").read_text(encoding="utf-8")
    # Production wrapper must scope both single-file and image-batch transient
    # identities and must restore monkey-patched helpers after rendering.
    for marker in [
        "_universal._file_token = scoped_file_token",
        "_extensions._batch_token = scoped_batch_token",
        "_universal._file_token = original_file_token",
        "_extensions._batch_token = original_batch_token",
        'key=f"v0151_post_import_image_dataset_{project_id}"',
        'if int(recent_target) != project_id:',
    ]:
        assert marker in source, marker

    print("universal intake project-scope tests: OK")


if __name__ == "__main__":
    main()

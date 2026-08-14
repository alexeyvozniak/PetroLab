from __future__ import annotations

from petrolab.formula_workflow import recommended_method


def main() -> None:
    assert recommended_method("mica").id == "mica_rieder_11o"  # type: ignore[union-attr]
    assert recommended_method("feldspar").id == "fsp_8o"  # type: ignore[union-attr]
    assert recommended_method("not_a_mineral") is None
    print("formula workflow tests: OK")


if __name__ == "__main__":
    main()

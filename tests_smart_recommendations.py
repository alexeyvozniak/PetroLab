from petrolab.ui.smart_plot_start import xy_recommendations


def main() -> None:
    mica = xy_recommendations(
        ["mica"],
        ["Al2O3", "TiO2", "FeO", "Mg#_formula", "Sample"],
        ["Al2O3", "TiO2", "FeO", "Mg#_formula"],
        limit=4,
    )
    assert [(item.x, item.y) for item in mica] == [
        ("Al2O3", "TiO2"),
        ("Mg#_formula", "TiO2"),
        ("Al2O3", "FeO"),
    ]
    assert all(item.route == "plots" for item in mica)

    # Missing columns make a candidate impossible; it must disappear rather than
    # being offered with a hidden calculation or guessed value.
    apatite = xy_recommendations(
        ["apatite"],
        ["F", "MnO", "SiO2", "TiO2"],
        ["F", "MnO", "SiO2", "TiO2"],
        limit=4,
    )
    assert all(item.x != "SrO" and item.y != "SrO" for item in apatite)
    assert all(item.x != "Cl" and item.y != "Cl" for item in apatite)

    # Mixed-mineral universes never borrow a mineral-specific interpretation.
    mixed = xy_recommendations(
        ["mica", "apatite"],
        ["SiO2", "TiO2", "Al2O3", "F", "Cl"],
        ["SiO2", "TiO2", "Al2O3", "F", "Cl"],
        limit=4,
    )
    assert len(mixed) == 1
    assert (mixed[0].x, mixed[0].y) == ("SiO2", "TiO2")
    assert "Нейтральный старт" in mixed[0].note

    print("Ranked scientific plot recommendations: OK")


if __name__ == "__main__":
    main()

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ThermobarometerMethod:
    """Minimum scientific provenance required before a P/T calibration can enter PetroLab."""

    method_id: str
    title: str
    equation_version: str
    source_citation: str
    source_doi: str
    required_components: tuple[str, ...]
    calibration_range: str
    uncertainty: str
    equilibrium_test: str
    assumptions: str = ""

    def validate(self) -> None:
        required_text = {
            "method_id": self.method_id,
            "title": self.title,
            "equation_version": self.equation_version,
            "source_citation": self.source_citation,
            "source_doi": self.source_doi,
            "calibration_range": self.calibration_range,
            "uncertainty": self.uncertainty,
            "equilibrium_test": self.equilibrium_test,
        }
        missing = [name for name, value in required_text.items() if not str(value).strip()]
        if not self.required_components:
            missing.append("required_components")
        if missing:
            raise ValueError(
                "Термометр/барометр нельзя зарегистрировать без полного scientific contract: "
                + ", ".join(missing)
            )
        doi = self.source_doi.strip().lower()
        if not doi.startswith("10.") or "/" not in doi:
            raise ValueError("source_doi должен быть DOI первичной публикации калибровки")


def validate_thermobarometer_registry(methods: tuple[ThermobarometerMethod, ...]) -> None:
    seen: set[str] = set()
    for method in methods:
        method.validate()
        if method.method_id in seen:
            raise ValueError(f"Повторный thermobarometer method_id: {method.method_id}")
        seen.add(method.method_id)

"""Семантика наблюдаемой текстурной зоны для импорта и разметки PetroLab."""
from __future__ import annotations


TEXTURAL_ZONE_COLUMN = "Textural zone"
SOURCE_TEXTURAL_ZONE_COLUMN = "Source Textural zone"
TEXTURAL_ZONE_ALIASES = (
    "textural zone",
    "textural position",
    "grain zone",
    "position in grain",
    "part of grain",
    "текстурная зона",
    "текстурная позиция",
    "зона зерна",
    "положение в зерне",
    "позиция в зерне",
    "часть зерна",
)
COMMON_TEXTURAL_ZONES = (
    "ядро",
    "серая кайма",
    "белая кайма",
    "внешняя кайма",
    "реакционная зона",
    "включение",
)


def install() -> None:
    """Отделить наблюдаемую текстуру от поздней интерпретации Generation."""
    from petrolab import import_staging, term_registry

    if TEXTURAL_ZONE_COLUMN not in import_staging.ROLE_ALIASES:
        updated: dict[str, tuple[str, ...]] = {}
        for role, aliases in import_staging.ROLE_ALIASES.items():
            updated[str(role)] = tuple(aliases)
            if role == "Mineral":
                updated[TEXTURAL_ZONE_COLUMN] = TEXTURAL_ZONE_ALIASES
        if TEXTURAL_ZONE_COLUMN not in updated:
            updated[TEXTURAL_ZONE_COLUMN] = TEXTURAL_ZONE_ALIASES
        import_staging.ROLE_ALIASES = updated

    if TEXTURAL_ZONE_COLUMN not in term_registry.DEFAULT_TERM_DOMAINS:
        domains: list[str] = []
        for domain in term_registry.DEFAULT_TERM_DOMAINS:
            if domain == "Generation":
                domains.append(TEXTURAL_ZONE_COLUMN)
            domains.append(str(domain))
        if TEXTURAL_ZONE_COLUMN not in domains:
            domains.append(TEXTURAL_ZONE_COLUMN)
        term_registry.DEFAULT_TERM_DOMAINS = tuple(domains)

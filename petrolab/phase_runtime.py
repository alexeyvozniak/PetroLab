from __future__ import annotations

from . import phase_suggestions as _phase


_ORIGINAL = _phase.mineral_key_for_phase


def _mineral_key_for_phase(label: str) -> str:
    """Map common petrographic phase names to the safest formula/storage family."""
    text = str(label or "").strip().casefold()
    if any(token in text for token in ("phlogop", "biotit", "biotite", "annite", "muscov", "флогоп", "биотит", "мусков")):
        return "mica"
    if any(token in text for token in ("magnet", "chromit", "spinel", "магнет", "хромит", "шпинел")):
        return "spinel"
    if "ilmen" in text or "ильмен" in text:
        return "fe_ti_oxide"
    if any(token in text for token in ("diop", "augite", "aegir", "hedenberg", "clinopyrox", "диопсид", "авгит", "эгирин", "клинопирокс")):
        return "clinopyroxene"
    if any(token in text for token in ("kaersut", "richter", "hornblend", "arfved", "amphib", "керсут", "рихтер", "рогов", "арфвед", "амфиб")):
        return "amphibole"
    if any(token in text for token in ("andrad", "melanite", "schorl", "grossular", "garnet", "андрад", "меланит", "гранат")):
        return "garnet"
    if any(token in text for token in ("forster", "fayalit", "oliv", "форстер", "фаялит", "олив")):
        return "olivine"
    return _ORIGINAL(label)


def install() -> None:
    _phase.mineral_key_for_phase = _mineral_key_for_phase

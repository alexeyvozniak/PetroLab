from dataclasses import replace

from .formulae import FormulaMethod, calculate_formula, methods_for
from . import registry as _registry
from .runtime_fixes import install_runtime_fixes

# Import/refresh descriptors must remain source-only. Scientific derivatives belong to
# the formula/derived layer where method and provenance are stored explicitly.
_registry.MINERALS = {
    key: replace(module, derive_basic_indices=False)
    for key, module in _registry.MINERALS.items()
}
MINERALS = _registry.MINERALS

install_runtime_fixes()

__all__ = ["FormulaMethod", "calculate_formula", "methods_for", "MINERALS"]

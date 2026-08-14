__version__ = "0.12.1"

from .measurement_policy import install as _install_measurement_policy
_install_measurement_policy()
del _install_measurement_policy

from .services.import_runtime import install as _install_import_runtime
_install_import_runtime()
del _install_import_runtime

from .ternary_runtime import install as _install_ternary_runtime
_install_ternary_runtime()
del _install_ternary_runtime

from .image_runtime import install as _install_image_runtime
_install_image_runtime()
del _install_image_runtime

from .minerals.formula_policy import install as _install_formula_policy
_install_formula_policy()
del _install_formula_policy

from .rock_runtime import install as _install_rock_runtime
_install_rock_runtime()
del _install_rock_runtime

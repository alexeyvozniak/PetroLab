__version__ = "0.15.9"

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

from .physical_point_safety import install as _install_physical_point_safety
_install_physical_point_safety()
del _install_physical_point_safety

from .amphibole_runtime import install as _install_amphibole_runtime
_install_amphibole_runtime()
del _install_amphibole_runtime

from .user_derived_runtime import install as _install_user_derived_runtime
_install_user_derived_runtime()
del _install_user_derived_runtime

from .textural_runtime import install as _install_textural_runtime
_install_textural_runtime()
del _install_textural_runtime

from .phase_runtime import install as _install_phase_runtime
_install_phase_runtime()
del _install_phase_runtime

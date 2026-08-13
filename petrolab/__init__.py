__version__ = "0.10.2"

from .measurement_policy import install as _install_measurement_policy

_install_measurement_policy()
del _install_measurement_policy

from .services.import_runtime import install as _install_import_runtime

_install_import_runtime()
del _install_import_runtime

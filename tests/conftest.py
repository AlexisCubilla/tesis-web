"""Deja importar `backend` desde los tests, y poder reimportarlo de verdad.

Pytest agrega al `sys.path` la carpeta que contiene el archivo de test —acá `tests/`—, no la raíz
del repositorio, así que sin esto `from backend import ...` no resuelve.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


def olvidar_backend() -> None:
    """Descarga el paquete `backend` entero para que el próximo import lo vuelva a ejecutar.

    Hace falta porque varios módulos resuelven rutas y abren bases **al importarse**
    (`ajustes.DIR_DATOS`, `cuentas.preparar()`), así que un test que quiera su propia carpeta de
    datos tiene que reimportarlos con el entorno ya cambiado.

    **Y hay que borrar el paquete, no solo sus submódulos.** Al importar `backend.cuentas`, Python
    además deja el módulo colgado como ATRIBUTO del paquete `backend`. Sacarlo de `sys.modules` no
    borra ese atributo, así que un `from . import cuentas` —que es lo que hace `main`— lo encuentra
    ahí y devuelve el módulo VIEJO sin reimportar nada. El resultado es un `main` hablando con la
    base del test anterior mientras el test mira otra: los dos coherentes por separado, y las
    aserciones fallando sin motivo visible. Costó encontrarlo una vez; queda escrito.
    """
    for nombre in [m for m in list(sys.modules) if m == "backend" or m.startswith("backend.")]:
        del sys.modules[nombre]

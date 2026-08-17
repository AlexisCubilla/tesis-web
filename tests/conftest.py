"""Deja importar `backend` desde los tests.

Pytest agrega al `sys.path` la carpeta que contiene el archivo de test —acá `tests/`—, no la raíz
del repositorio, así que sin esto `from backend import ...` no resuelve.
"""

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

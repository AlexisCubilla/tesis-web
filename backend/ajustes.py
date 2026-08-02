"""Configuración del taller, leída del entorno (o de un archivo `.env` en la raíz del repo).

Todo lo que depende de la máquina o del gusto de quien lo corre vive acá: dónde está el repo de la
tesis, dónde se guarda el estado local, en qué puerto se sirve. Nada de eso debería estar escrito a
mano en el código, porque no todo el mundo tiene los repos con el mismo nombre ni en el mismo lugar.

Ver `.env.example` para la lista completa con sus valores por defecto.
"""

from __future__ import annotations

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

# `python-dotenv` viene con uvicorn[standard], así que no suma una dependencia nueva.
try:
    from dotenv import load_dotenv

    load_dotenv(RAIZ / ".env")
except ImportError:  # sin dotenv se usan solo las variables ya exportadas en el entorno
    pass


def _ruta(nombre: str, defecto: str) -> Path:
    """Lee una ruta del entorno. Las relativas se resuelven contra la raíz del repo, no contra el cwd."""
    valor = os.environ.get(nombre, "").strip() or defecto
    p = Path(valor).expanduser()
    return p if p.is_absolute() else (RAIZ / p).resolve()


def _num(nombre: str, defecto: float) -> float:
    try:
        return float(os.environ.get(nombre, "").strip() or defecto)
    except ValueError:
        return defecto


def ruta_tesis() -> Path:
    """Dónde está el repositorio de la tesis.

    Se prefiere deducirlo del paquete ya instalado (`pip install -e …`), porque así funciona sin
    importar cómo se llame la carpeta o dónde esté. `RUTA_TESIS` es el respaldo, y es la que usan
    `mise` y `podman compose` para instalarlo y montarlo.
    """
    try:
        import tesis

        return Path(tesis.__file__).resolve().parents[2]
    except Exception:
        return _ruta("RUTA_TESIS", "../repo-rebuild")


#: Carpeta con el estado local: tabla cruda, caché de etapas y base SQLite.
DIR_DATOS: Path = _ruta("DIR_DATOS", "data")
DIR_CACHE: Path = DIR_DATOS / "cache"
BASE_SQLITE: Path = DIR_DATOS / "ejecuciones.sqlite"
TABLA_CRUDA: Path = DIR_DATOS / "crudo.joblib"

#: Carpeta del frontend.
DIR_WEB: Path = _ruta("DIR_WEB", "web")

#: Puerto por defecto (lo usan las tareas de mise y el compose; uvicorn puede recibir otro).
PUERTO: int = int(_num("PUERTO", 8000))

#: Intervalo real entre mediciones, en segundos. Se usa solo para traducir "50 mediciones" a minutos
#: en los textos de la interfaz. En los datos varía entre 10 y 11,3 s según la hoja.
MUESTREO_SEGUNDOS: float = _num("MUESTREO_SEGUNDOS", 10.6)

#: Configuración de referencia: los valores con los que la tesis reporta sus resultados. No son "los
#: correctos": son los que los autores y la tutoría fijaron y dejaron justificados por escrito. El
#: taller los muestra como referencia y marca con ★ las ramas que coinciden.
CONFIG_TESIS: dict[str, dict] = {
    "datos": {"limpiar": True},
    "ventaneo": {
        "tamano_ventana": int(_num("TESIS_VENTANA", 50)),
        "paso": int(_num("TESIS_PASO", 1)),
        "deduplicar": os.environ.get("TESIS_DEDUP", "1").strip() not in ("0", "false", "no"),
        "umbral_dedup": _num("TESIS_UMBRAL_DEDUP", 0.95),
    },
    "features": {},
    "filtrado": {},
    "deteccion": {},
    "eventos": {
        "fraccion_candidatos": _num("TESIS_FRACCION_CANDIDATOS", 0.01),
        "max_ventanas_evento": int(_num("TESIS_TOPE_EVENTO", 15)),
    },
}

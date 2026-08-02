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

def _bool(nombre: str, defecto: bool) -> bool:
    valor = os.environ.get(nombre, "").strip().lower()
    if not valor:
        return defecto
    return valor not in ("0", "false", "no")


#: Respaldo si el paquete de la tesis todavía no está instalado (por ejemplo, al correr `mise run
#: check` antes de `mise run install`). Son los valores vigentes al escribir esto; la fuente real es
#: `config.py` de la tesis.
_RESPALDO: dict[str, dict] = {
    "datos": {"limpiar": True, "hojas_excluidas": ["Test1 w batt", "Test2 wo batt", "Anomalous data"]},
    "ventaneo": {"tamano_ventana": 50, "paso": 1, "deduplicar": True, "umbral_dedup": 0.95},
    "features": {"rezagos_autocorr": 5},
    "filtrado": {"umbral_correlacion": 0.95, "percentil_baja_var": 5.0},
    "deteccion": {"detectores": ["isolation_forest", "ecod", "copod", "pca", "hdbscan_glosh"],
                  "arboles_iforest": 300, "min_cluster_hdbscan": 15},
    "eventos": {"fraccion_candidatos": 0.01, "max_ventanas_evento": 15},
}


#: De dónde salieron los valores de referencia en la última llamada a `config_tesis()`.
_origen: dict[str, str | None] = {"fuente": "sin resolver", "problema": None}


def origen_config() -> dict:
    """De dónde salió la configuración de referencia y, si hubo problema, cuál fue."""
    return dict(_origen)


def config_tesis() -> dict[str, dict]:
    """La configuración de referencia: los valores con los que la tesis reporta sus resultados.

    **Sale del propio paquete de la tesis** (`tesis.config.CONFIG`), que según las reglas de ese
    repositorio es la fuente única de verdad de todos los parámetros. Así, cuando allá se firma un
    cambio por ADR —como pasó con el tope de 15 ventanas por evento—, el taller se actualiza solo: el
    botón "★ Correr la de la tesis", la marca ★ de las ramas y los valores iniciales de los
    formularios quedan sincronizados sin tocar nada acá.

    Las variables `TESIS_*` del entorno **solo se usan si están definidas**, para poder mostrar otra
    configuración de referencia sin modificar la tesis. Normalmente se dejan sin definir.

    No son "los valores correctos": son los que los autores y la tutoría eligieron y justificaron.
    """
    try:
        from tesis.config import CONFIG

        base = {
            "datos": {
                "limpiar": True,
                "hojas_excluidas": list(CONFIG.data.excluded_sheets),
            },
            "ventaneo": {
                "tamano_ventana": CONFIG.window.window_size,
                "paso": CONFIG.window.stride,
                "deduplicar": CONFIG.window.use_dedup,
                "umbral_dedup": CONFIG.window.dedup_threshold,
            },
            "features": {"rezagos_autocorr": len(CONFIG.features.autocorr_lags)},
            "filtrado": {
                "umbral_correlacion": CONFIG.filtering.correlation_threshold,
                "percentil_baja_var": CONFIG.filtering.lowvar_percentile,
            },
            "deteccion": {
                "detectores": list(CONFIG.detection.detectors),
                "arboles_iforest": CONFIG.detection.iforest_n_estimators,
                "min_cluster_hdbscan": CONFIG.detection.hdbscan_min_cluster_size,
            },
            "eventos": {
                "fraccion_candidatos": CONFIG.detection.candidate_fraction,
                # En la tesis "sin tope" es None; en la interfaz es 0, que se puede escribir en un campo.
                "max_ventanas_evento": CONFIG.detection.max_event_windows or 0,
            },
        }
        _origen["fuente"] = "paquete de la tesis"
        _origen["problema"] = None
    except Exception as e:
        # Nunca en silencio: si se cae acá, el taller mostraría valores de respaldo como si fueran los
        # de la tesis. Se registra el motivo y `verificar.py` y /api/estado lo informan.
        base = {k: dict(v) for k, v in _RESPALDO.items()}
        _origen["fuente"] = "respaldo (valores fijos del taller)"
        _origen["problema"] = f"{type(e).__name__}: {e}"

    # Overrides opcionales del entorno. Solo pisan lo que esté explícitamente definido.
    sobreescribir = {
        ("ventaneo", "tamano_ventana"): ("TESIS_VENTANA", int),
        ("ventaneo", "paso"): ("TESIS_PASO", int),
        ("ventaneo", "deduplicar"): ("TESIS_DEDUP", bool),
        ("ventaneo", "umbral_dedup"): ("TESIS_UMBRAL_DEDUP", float),
        ("features", "rezagos_autocorr"): ("TESIS_REZAGOS", int),
        ("filtrado", "umbral_correlacion"): ("TESIS_UMBRAL_CORRELACION", float),
        ("eventos", "fraccion_candidatos"): ("TESIS_FRACCION_CANDIDATOS", float),
        ("eventos", "max_ventanas_evento"): ("TESIS_TOPE_EVENTO", int),
    }
    pisados = []
    for (etapa, clave), (var, tipo) in sobreescribir.items():
        if os.environ.get(var, "").strip():
            base[etapa][clave] = _bool(var, True) if tipo is bool else tipo(_num(var, 0))
            pisados.append(var)
    _origen["sobreescritos"] = ", ".join(pisados) if pisados else None
    return base


#: Se resuelve al importar: el paquete de la tesis ya está instalado en condiciones normales.
CONFIG_TESIS: dict[str, dict] = config_tesis()

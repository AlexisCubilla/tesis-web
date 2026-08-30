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

# --------------------------------------------------------------------------------------
# Revisión experta (OnlyOffice)
# --------------------------------------------------------------------------------------
# El editor necesita TRES direcciones distintas, y confundirlas es el error clásico: no todos los
# que participan ven al otro con el mismo nombre.
#
#   navegador ──── OO_URL_PUBLICA ────→ Document Server   (carga el editor)
#   navegador ──────────────────────→ taller             (esta app)
#   Document Server ── OO_URL_DEL_TALLER ──→ taller       (baja el archivo y avisa al guardar)
#
# La tercera es la que se escapa: el Document Server corre en OTRO contenedor, así que para él
# `localhost` es él mismo, no el taller. En desarrollo con podman se ven por nombre de servicio
# (http://taller:8000); en el servidor será el nombre real de la máquina.


def _bool_temprano(nombre: str, defecto: bool) -> bool:
    """Igual que `_bool`, pero definido acá arriba porque se usa antes."""
    valor = os.environ.get(nombre, "").strip().lower()
    return defecto if not valor else valor not in ("0", "false", "no")


def _url(nombre: str, defecto: str = "") -> str:
    """Lee una URL del entorno y le saca la barra final, para poder concatenar sin dudar."""
    return (os.environ.get(nombre, "").strip() or defecto).rstrip("/")


#: Dónde carga el navegador el editor.
#:
#: **Vacío es lo normal y significa «por el mismo origen que el taller»**: el propio taller le hace
#: de proxy al Document Server (ver `proxy_oo.py`). Eso evita que el editor quede en un marco de otro
#: origen, que es lo que Firefox castiga partiéndole el almacenamiento hasta dejarlo sin arrancar.
#:
#: Se le pone una URL solo si se quiere ir DERECHO al Document Server, sin pasar por el taller.
OO_URL_PUBLICA: str = _url("OO_URL_PUBLICA")

#: Con qué dirección el Document Server ve a este taller. Sin esto no puede bajar el archivo ni
#: avisar cuando el experto guarda, así que la edición no funcionaría.
#:
#: No tiene valor por defecto a propósito: `http://taller:8000` solo significa algo adentro del
#: compose, y como respaldo general haría que la revisión pareciera configurada en un servidor donde
#: no lo está. El compose la define explícitamente.
OO_URL_DEL_TALLER: str = _url("OO_URL_DEL_TALLER")

#: Con qué dirección este taller ve al Document Server. Hace falta porque al guardar, el editor
#: NO manda el archivo: manda una URL suya para que lo vayamos a buscar, y a veces esa URL viene con
#: un nombre que solo él entiende. Si está definida, se le reemplaza el origen a esa URL.
OO_URL_INTERNA: str = _url("OO_URL_INTERNA")

#: Secreto JWT del Document Server. Vacío = sin firma (es lo que se usa en desarrollo).
OO_JWT_SECRETO: str = os.environ.get("OO_JWT_SECRETO", "").strip()

#: Idioma y formato del editor.
OO_IDIOMA: str = os.environ.get("OO_IDIOMA", "es").strip() or "es"


#: Servir el Document Server a través del taller, en el mismo origen. Es lo que hay que querer casi
#: siempre; se apaga solo para depurar contra el servidor directo.
OO_PROXY: bool = _bool_temprano("OO_PROXY", True)


def url_para_el_navegador() -> str:
    """Con qué prefijo el navegador pide el editor.

    Cadena vacía = mismo origen, que es lo que hace que el marco no sea de un tercero.
    """
    return "" if OO_PROXY and not OO_URL_PUBLICA else OO_URL_PUBLICA


def motivo_revision_apagada() -> str | None:
    """Por qué la revisión experta no está disponible, o None si sí lo está.

    Hacen falta las dos direcciones y no alcanza con una: una para que el taller (o el navegador)
    llegue al Document Server, y otra para que el Document Server llegue de vuelta al taller. Con una
    sola, el editor abre y después no puede ni bajar el archivo ni avisar cuando se guarda.
    """
    if not (OO_URL_INTERNA or OO_URL_PUBLICA):
        return ("falta OO_URL_INTERNA (o OO_URL_PUBLICA): no hay Document Server configurado")
    if not OO_URL_DEL_TALLER:
        return ("falta OO_URL_DEL_TALLER: el Document Server no sabría con qué dirección volver "
                "a este taller para bajar el archivo y avisar de los guardados")
    return None


def revision_habilitada() -> bool:
    """¿Está configurada la revisión experta? Sin Document Server el taller funciona igual, pero
    sin la pantalla de comentarios."""
    return motivo_revision_apagada() is None


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
    botón "★ Ejecutar tesis", la marca ★ de las ramas y los valores iniciales de los
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

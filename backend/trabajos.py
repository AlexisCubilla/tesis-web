"""Ejecución en segundo plano.

Una corrida completa tarda decenas de segundos, así que no puede resolverse dentro de una petición
HTTP. El flujo es: la petición **encola** el trabajo y devuelve la clave; un hilo trabajador lo
ejecuta; el estado queda en SQLite; el frontend pregunta cada tanto cómo va.

Un solo hilo trabajador a propósito: las etapas ya usan todos los núcleos internamente (los detectores
paralelizan), así que correr dos a la vez solo se pelearía por la CPU.
"""

from __future__ import annotations

import queue
import threading
import time
import traceback

from . import almacen, etapas

_cola: "queue.Queue[str]" = queue.Queue()
_trabajador: threading.Thread | None = None


def encolar(clave: str) -> None:
    _cola.put(clave)


def iniciar_trabajador(con) -> None:
    global _trabajador
    if _trabajador is not None and _trabajador.is_alive():
        return
    _trabajador = threading.Thread(target=_bucle, args=(con,), daemon=True, name="ejecutor")
    _trabajador.start()


def _bucle(con) -> None:
    while True:
        clave = _cola.get()
        try:
            _ejecutar_nodo(con, clave)
        except Exception:  # el trabajador nunca muere por un error de una tarea
            almacen.marcar(con, clave, "error", error=traceback.format_exc(limit=6))
        finally:
            _cola.task_done()


def _ejecutar_nodo(con, clave: str) -> None:
    nodo = almacen.obtener(con, clave)
    if nodo is None or nodo["estado"] == "listo":
        return

    almacen.marcar(con, clave, "corriendo")
    inicio = time.time()
    try:
        entrada = _entrada_de(con, nodo)
        etapa = etapas.REGISTRO[nodo["etapa"]]
        salida, resumen = etapa.ejecutar(entrada, nodo["parametros"])
        almacen.guardar_resultado(clave, salida)
        almacen.marcar(con, clave, "listo", resumen=resumen, duracion=round(time.time() - inicio, 2))
    except Exception:
        almacen.marcar(con, clave, "error", error=traceback.format_exc(limit=6),
                       duracion=round(time.time() - inicio, 2))


def _entrada_de(con, nodo: dict):
    """Recupera la salida del nodo padre; si es la primera etapa, la tabla cruda precalculada.

    Si el padre no tiene su resultado en caché (por ejemplo, porque se borró la carpeta), se
    reconstruye recursivamente ejecutando la cadena desde donde haga falta.
    """
    import joblib

    padre = nodo["padre"]
    if padre is None:
        if not almacen.TABLA_CRUDA.exists():
            raise FileNotFoundError(
                f"No existe {almacen.TABLA_CRUDA}. Generala con: python scripts/exportar_crudo.py"
            )
        return joblib.load(almacen.TABLA_CRUDA)

    if not almacen.hay_resultado(padre):
        _ejecutar_nodo(con, padre)
        if not almacen.hay_resultado(padre):
            raise RuntimeError(f"El nodo padre {padre} no pudo ejecutarse")
    return almacen.cargar_resultado(padre)

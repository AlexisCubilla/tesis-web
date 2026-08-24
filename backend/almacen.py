"""Almacenamiento: el árbol de ejecuciones (SQLite) y el caché de resultados (archivos en disco).

Dos piezas separadas a propósito:

  - **SQLite** guarda el árbol: qué configuración, de qué nodo viene, en qué estado está y un resumen
    chico de números. Son pocos miles de filas y un solo usuario: no hace falta un servidor de base de
    datos. Todo el estado vive en un archivo que se puede copiar o borrar.
  - **Disco** guarda los resultados pesados (tensores de ventanas, matrices de features, scores) con
    `joblib`. En la base solo queda la referencia. Meter matrices dentro de la base es el error clásico.

**Cómo funcionan las ramas.** Cada nodo se identifica por un hash de su etapa, sus parámetros y la
clave de su padre. Dos configuraciones que comparten el tramo inicial producen las mismas claves en
ese tramo, así que **reutilizan el caché sin que haya que programar nada**: la ramificación es una
consecuencia del encadenamiento de hashes, no una estructura que haya que mantener.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ajustes

RAIZ = ajustes.RAIZ
DIR_DATOS = ajustes.DIR_DATOS
DIR_CACHE = ajustes.DIR_CACHE
BASE = ajustes.BASE_SQLITE
TABLA_CRUDA = ajustes.TABLA_CRUDA

_lock = threading.Lock()

ESQUEMA = """
CREATE TABLE IF NOT EXISTS nodos (
    clave        TEXT PRIMARY KEY,
    etapa        TEXT NOT NULL,
    padre        TEXT,
    parametros   TEXT NOT NULL,
    estado       TEXT NOT NULL,
    resumen      TEXT,
    error        TEXT,
    creado_en    TEXT NOT NULL,
    terminado_en TEXT,
    duracion_s   REAL,
    commit_tesis TEXT,
    etiqueta     TEXT
);
CREATE INDEX IF NOT EXISTS idx_nodos_padre ON nodos(padre);
"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar() -> sqlite3.Connection:
    DIR_DATOS.mkdir(parents=True, exist_ok=True)
    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(BASE, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.executescript(ESQUEMA)
    return con


def clave_nodo(etapa: str, parametros: dict, padre: str | None) -> str:
    """Hash determinista de (etapa, parámetros, padre).

    Es la pieza central del caché: la misma configuración siempre da la misma clave, así que pedir dos
    veces lo mismo devuelve el resultado guardado. Los parámetros se serializan ordenados para que el
    orden de las claves del diccionario no cambie el hash.
    """
    material = json.dumps(
        {"etapa": etapa, "parametros": parametros, "padre": padre},
        sort_keys=True, ensure_ascii=False, default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def ruta_cache(clave: str) -> Path:
    return DIR_CACHE / f"{clave}.joblib"


def hay_resultado(clave: str) -> bool:
    return ruta_cache(clave).exists()


def guardar_resultado(clave: str, valor: Any) -> None:
    import joblib

    DIR_CACHE.mkdir(parents=True, exist_ok=True)
    joblib.dump(valor, ruta_cache(clave), compress=3)


def cargar_resultado(clave: str) -> Any:
    import joblib

    return joblib.load(ruta_cache(clave))


def commit_tesis() -> str:
    """Commit del repo de la tesis con el que se ejecutó. Queda registrado en cada nodo.

    Sirve para saber con qué versión del pipeline se generó cada rama: si el paquete cambia, los
    resultados viejos siguen identificados con el código que los produjo. La ubicación del repo se
    deduce del paquete instalado, así que no depende de cómo se llame la carpeta.
    """
    import subprocess

    try:
        r = subprocess.run(
            ["git", "-C", str(ajustes.ruta_tesis()), "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return r.stdout.strip() or "desconocido"
    except Exception:
        return "desconocido"


# --------------------------------------------------------------------------------------
# Operaciones sobre el árbol
# --------------------------------------------------------------------------------------

def crear_nodo(con, clave: str, etapa: str, padre: str | None, parametros: dict,
               etiqueta: str | None = None) -> None:
    with _lock:
        con.execute(
            "INSERT OR IGNORE INTO nodos "
            "(clave, etapa, padre, parametros, estado, creado_en, commit_tesis, etiqueta) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (clave, etapa, padre, json.dumps(parametros, ensure_ascii=False),
             "pendiente", _ahora(), commit_tesis(), etiqueta),
        )
        con.commit()


def marcar(con, clave: str, estado: str, *, resumen: dict | None = None,
           error: str | None = None, duracion: float | None = None) -> None:
    with _lock:
        con.execute(
            "UPDATE nodos SET estado=?, resumen=COALESCE(?, resumen), error=?, "
            "terminado_en=?, duracion_s=COALESCE(?, duracion_s) WHERE clave=?",
            (estado,
             json.dumps(resumen, ensure_ascii=False) if resumen is not None else None,
             error,
             _ahora() if estado in ("listo", "error") else None,
             duracion, clave),
        )
        con.commit()


def etiquetar(con, clave: str, etiqueta: str | None) -> None:
    """Le pone (o le saca) un nombre a un paso.

    El mapa muestra las ramas por su configuración —`50/1 · 0,95`—, que es preciso pero anónimo.
    Cuando hay diez, poder llamarlas «la que le mostré a Jara» o «sin dedup» es lo que las vuelve
    recordables. No entra en el hash: es una etiqueta para humanos, no parte de la identidad del
    resultado, así que renombrar no invalida el caché ni crea una rama nueva.
    """
    with _lock:
        con.execute("UPDATE nodos SET etiqueta=? WHERE clave=?", (etiqueta or None, clave))
        con.commit()


def obtener(con, clave: str) -> dict | None:
    fila = con.execute("SELECT * FROM nodos WHERE clave=?", (clave,)).fetchone()
    return _fila_a_dict(fila) if fila else None


def listar(con) -> list[dict]:
    filas = con.execute("SELECT * FROM nodos ORDER BY creado_en").fetchall()
    return [_fila_a_dict(f) for f in filas]


def descendientes(con, clave: str) -> list[str]:
    """Todas las claves que cuelgan de `clave`, en profundidad (sin incluirla)."""
    salida: list[str] = []
    pendientes = [clave]
    while pendientes:
        actual = pendientes.pop()
        hijos = [f["clave"] for f in
                 con.execute("SELECT clave FROM nodos WHERE padre=?", (actual,)).fetchall()]
        salida.extend(hijos)
        pendientes.extend(hijos)
    return salida


def borrar(con, clave: str) -> dict:
    """Borra un nodo, todo lo que cuelga de él y sus resultados en disco.

    Se borra en cascada a propósito: un nodo hijo sin su padre no se puede reconstruir ni interpretar,
    así que dejarlo huérfano solo ensuciaría el árbol.
    """
    claves = [clave, *descendientes(con, clave)]
    liberado = 0
    for k in claves:
        ruta = ruta_cache(k)
        if ruta.exists():
            liberado += ruta.stat().st_size
            ruta.unlink()
    with _lock:
        con.executemany("DELETE FROM nodos WHERE clave=?", [(k,) for k in claves])
        con.commit()
    return {"borrados": len(claves), "bytes_liberados": liberado}


def cadena_hasta(con, clave: str) -> list[dict]:
    """Los nodos desde la raíz hasta `clave`, en orden. Es la configuración completa de una rama."""
    cadena: list[dict] = []
    actual = obtener(con, clave)
    while actual is not None:
        cadena.append(actual)
        actual = obtener(con, actual["padre"]) if actual["padre"] else None
    return list(reversed(cadena))


def _fila_a_dict(f: sqlite3.Row) -> dict:
    d = dict(f)
    d["parametros"] = json.loads(d["parametros"]) if d["parametros"] else {}
    d["resumen"] = json.loads(d["resumen"]) if d["resumen"] else None
    d["tiene_resultado"] = hay_resultado(d["clave"])
    return d

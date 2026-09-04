"""Clasificación de eventos: lo que cada revisor opina de cada evento candidato.

Esto es la Etapa 2 entrando por la puerta chica. El pipeline entrega eventos candidatos; acá una
persona los mira uno por uno y dice si le parecen anómalos. Es la misma materia prima que
`revision.py` recoge en formato planilla, pero estructurada: cinco opciones y un comentario, en vez
de texto libre en una celda.

**Las dos formas conviven a propósito y no se pisan.** La planilla no encajona al experto y por eso
sirve para que produzca la taxonomía de la Etapa 2, que es trabajo suyo. Esta encuesta hace la
pregunta previa —¿esto es una anomalía, sí o no?— que sí tiene una respuesta cerrada y que hace
falta poder contar, comparar entre revisores y llevar a un reporte.

**Es por persona, no global.** La clave incluye al usuario: dos revisores clasifican el mismo evento
sin verse. Eso es un requisito, no una comodidad — la coincidencia entre revisores independientes
es la única forma de medir si la pregunta está bien planteada, y se pierde si el segundo ve la
respuesta del primero.

**Es por rama.** La clave es `(nodo, event_id)`: la clasificación pertenece a la corrida donde se
hizo. Un evento con otro dedup o con otra fracción de candidatos **no es el mismo evento** —tiene
otro rango, otras ventanas y otra prioridad—, así que heredarle la respuesta sería inventar un
juicio que nadie emitió. El costo asumido es que explorar ramas obliga a reclasificar.

**Guarda una copia de los datos del evento.** Hoja, segmento, rango, tramos y prioridad se copian
en la fila. La respuesta tiene que seguir siendo legible aunque la rama se borre y el evento deje
de poder consultarse: sin eso, borrar una rama dejaría opiniones sobre un identificador que ya no
resuelve a nada. Es la misma decisión que toma `revision.py` con los documentos huérfanos.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from . import ajustes

#: Junto a lo demás que no se recalcula. `mise run limpiar` no lo toca.
DIR_CLASIFICACION: Path = ajustes.DIR_DATOS / "revision"
BASE: Path = DIR_CLASIFICACION / "clasificacion.sqlite"

#: La escala, en un solo lugar.
#:
#: En la base se guarda el `codigo`, no la etiqueta: es lo que permite traducir la interfaz sin
#: reescribir los datos, y lo que evita que un cambio de redacción parta el histórico en dos. El
#: `valor` es el orden de la escala, para promediar y ordenar en los reportes.
ESCALA: tuple[dict, ...] = (
    {"codigo": "no_definitivo", "etiqueta": "Definitivamente no", "valor": -2},
    {"codigo": "no",            "etiqueta": "No",                 "valor": -1},
    {"codigo": "neutral",       "etiqueta": "Neutral",            "valor": 0},
    {"codigo": "si",            "etiqueta": "Sí",                 "valor": 1},
    {"codigo": "si_definitivo", "etiqueta": "Definitivamente sí", "valor": 2},
)

CODIGOS: frozenset[str] = frozenset(o["codigo"] for o in ESCALA)

#: La pregunta vive con la escala. Si algún día hay más de un idioma, esto es lo que se traduce.
PREGUNTA = "¿Este evento representa un comportamiento anómalo?"

#: Tope del comentario. No es una restricción de la base: es para que un pegado accidental de media
#: planilla no entre como si fuera una observación.
MAX_COMENTARIO = 4000

_lock = threading.Lock()
_con: sqlite3.Connection | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS clasificaciones (
    nodo          TEXT NOT NULL,
    event_id      INTEGER NOT NULL,
    usuario       TEXT NOT NULL,
    respuesta     TEXT NOT NULL,
    comentario    TEXT NOT NULL DEFAULT '',
    creado_en     TEXT NOT NULL,
    actualizado_en TEXT NOT NULL,
    hoja          TEXT,
    segmento      TEXT,
    desde         INTEGER,
    hasta         INTEGER,
    n_ventanas    INTEGER,
    n_detectores  INTEGER,
    PRIMARY KEY (nodo, event_id, usuario)
);
CREATE INDEX IF NOT EXISTS idx_clas_nodo    ON clasificaciones(nodo);
CREATE INDEX IF NOT EXISTS idx_clas_usuario ON clasificaciones(usuario);
"""


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def preparar() -> sqlite3.Connection:
    global _con
    if _con is not None:
        return _con
    DIR_CLASIFICACION.mkdir(parents=True, exist_ok=True)
    _con = sqlite3.connect(BASE, check_same_thread=False)
    _con.row_factory = sqlite3.Row
    _con.executescript(ESQUEMA)
    return _con


def conexion() -> sqlite3.Connection:
    return _con if _con is not None else preparar()


def guardar(
    nodo: str,
    event_id: int,
    usuario: str,
    respuesta: str,
    comentario: str = "",
    *,
    evento: dict | None = None,
) -> dict:
    """Registra (o corrige) la respuesta de una persona sobre un evento.

    Cambiar de opinión pisa la respuesta anterior pero **conserva `creado_en`**: interesa cuándo se
    miró el evento por primera vez, no solo la última corrección. `evento` es la copia de contexto
    descrita en el encabezado del módulo; solo se escribe en el alta, para que una corrección no
    pueda reescribir el rango con datos de otra corrida.
    """
    if respuesta not in CODIGOS:
        raise ValueError(f"Respuesta desconocida: {respuesta!r}")
    comentario = (comentario or "").strip()[:MAX_COMENTARIO]
    ev = evento or {}
    ahora = _ahora()
    con = conexion()
    with _lock:
        con.execute(
            """INSERT INTO clasificaciones
                 (nodo, event_id, usuario, respuesta, comentario, creado_en, actualizado_en,
                  hoja, segmento, desde, hasta, n_ventanas, n_detectores)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(nodo, event_id, usuario) DO UPDATE SET
                 respuesta = excluded.respuesta,
                 comentario = excluded.comentario,
                 actualizado_en = excluded.actualizado_en""",
            (nodo, int(event_id), usuario, respuesta, comentario, ahora, ahora,
             ev.get("SheetName"), ev.get("segment"), ev.get("start"), ev.get("end"),
             ev.get("n_ventanas"), ev.get("n_detectores")),
        )
        con.commit()
    return mia(nodo, int(event_id), usuario) or {}


def mia(nodo: str, event_id: int, usuario: str) -> dict | None:
    """La respuesta de una persona sobre un evento, o `None` si todavía no lo clasificó."""
    fila = conexion().execute(
        "SELECT * FROM clasificaciones WHERE nodo = ? AND event_id = ? AND usuario = ?",
        (nodo, int(event_id), usuario),
    ).fetchone()
    return dict(fila) if fila is not None else None


def del_nodo(nodo: str, usuario: str) -> dict[int, dict]:
    """Todo lo que una persona clasificó en una rama, por `event_id`.

    Lo usa la tabla de eventos para marcar de un vistazo qué queda por revisar, que es lo primero
    que se necesita cuando hay que pasar por cuarenta eventos en varias sesiones.
    """
    filas = conexion().execute(
        "SELECT * FROM clasificaciones WHERE nodo = ? AND usuario = ?", (nodo, usuario)
    ).fetchall()
    return {int(f["event_id"]): dict(f) for f in filas}


def de_evento(nodo: str, event_id: int) -> list[dict]:
    """Todas las respuestas sobre un evento, de todos los revisores. Base de los reportes."""
    filas = conexion().execute(
        """SELECT usuario, respuesta, comentario, creado_en, actualizado_en
           FROM clasificaciones WHERE nodo = ? AND event_id = ? ORDER BY usuario""",
        (nodo, int(event_id)),
    ).fetchall()
    return [dict(f) for f in filas]


def resumen_nodo(nodo: str) -> dict:
    """Cuántas respuestas hay en una rama y cómo se reparten. Para el encabezado de la tabla."""
    filas = conexion().execute(
        """SELECT respuesta, COUNT(*) AS n, COUNT(DISTINCT usuario) AS revisores
           FROM clasificaciones WHERE nodo = ? GROUP BY respuesta""",
        (nodo,),
    ).fetchall()
    reparto = {f["respuesta"]: int(f["n"]) for f in filas}
    revisores = conexion().execute(
        "SELECT COUNT(DISTINCT usuario) AS n FROM clasificaciones WHERE nodo = ?", (nodo,)
    ).fetchone()
    return {
        "total": sum(reparto.values()),
        "reparto": reparto,
        "revisores": int(revisores["n"]),
    }


def cuantas_en(nodos: list[str]) -> int:
    """Cuántas clasificaciones cuelgan de un conjunto de ramas.

    La usa el borrado en cascada para poder avisar antes de llevarse por delante trabajo humano,
    igual que ya hace con los documentos de revisión.
    """
    if not nodos:
        return 0
    marcas = ",".join("?" * len(nodos))
    fila = conexion().execute(
        f"SELECT COUNT(*) AS n FROM clasificaciones WHERE nodo IN ({marcas})", nodos
    ).fetchone()
    return int(fila["n"])

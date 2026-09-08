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

**Se va con su rama.** Borrar la rama borra sus clasificaciones (`borrar_de`), y lo que protege el
trabajo es el aviso previo: `delete_nodo` se planta con un 409 que dice cuántas hay y exige
`forzar`. Hubo un intento anterior de conservarlas —la fila sobrevivía a la rama, y seis columnas
copiaban hoja, segmento y rango para que siguiera siendo legible— que se revirtió porque estaba a
medio hacer: no había forma de LLEGAR a una fila huérfana. La única llave era el `nodo`, un hash de
16 caracteres que desaparecía del árbol justo al borrarlo, y no existía listado ni pantalla que las
mostrara. `revision.py` sí tiene las dos cosas para sus documentos, y por eso ahí conservar
funciona; acá conservar era guardar un dato que nadie podía volver a ver.

Que se vaya con la rama además es coherente con «es por rama», más arriba: si el juicio pertenece a
la corrida donde se emitió, sin esa corrida no hay juicio que recuperar.

**Los dos borrados que sí existen, y quién los decide.** `retirar()` es una persona sacando su
propia respuesta —la clave incluye al usuario, así que nadie toca la de otro—. `borrar_de()` es la
rama entera yéndose, con el 409 de por medio. Lo que NO borra nada es dar de baja una cuenta: ahí
el juicio queda, porque nadie eligió deshacerse de él y sigue contando para la coincidencia entre
revisores.
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
    respuesta     TEXT,
    comentario    TEXT NOT NULL DEFAULT '',
    creado_en     TEXT NOT NULL,
    actualizado_en TEXT NOT NULL,
    PRIMARY KEY (nodo, event_id, usuario)
);
CREATE INDEX IF NOT EXISTS idx_clas_nodo    ON clasificaciones(nodo);
CREATE INDEX IF NOT EXISTS idx_clas_usuario ON clasificaciones(usuario);
"""

#: Las seis columnas que copiaban el evento. Ver `_migrar` justo abajo.
_COLUMNAS_MUERTAS = ("hoja", "segmento", "desde", "hasta", "n_ventanas", "n_detectores")


def _migrar(con: sqlite3.Connection) -> list[str]:
    """Quita las columnas que copiaban el evento, si la base viene de antes.

    Estaban para que una clasificación siguiera siendo legible después de borrar su rama. Eso ya no
    pasa —borrar la rama borra las clasificaciones, ver `borrar_de`— así que las seis columnas no
    tienen para qué existir. Y en los hechos nunca lo tuvieron: se escribían en cada alta y no las
    leía nadie, ni el backend ni el frontend.

    Corre en cada arranque y es idempotente: pregunta qué columnas hay antes de tocar nada. Es el
    mismo criterio que `cuentas._sembrar_admin`, y sirve para lo mismo: que actualizar el código sea
    suficiente y no haya un paso manual que alguien tenga que recordar dentro de dos años.

    `DROP COLUMN` necesita SQLite 3.35 (2021). Si la base es más vieja que eso, las columnas se
    quedan ahí sin molestar: `guardar` nombra las suyas explícitamente y estas admiten NULL.
    """
    hay = {f["name"] for f in con.execute("PRAGMA table_info(clasificaciones)")}
    quitadas = []
    for col in _COLUMNAS_MUERTAS:
        if col not in hay:
            continue
        try:
            con.execute(f"ALTER TABLE clasificaciones DROP COLUMN {col}")
            quitadas.append(col)
        except sqlite3.OperationalError:
            break     # SQLite viejo: se quedan, y no pasa nada
    if quitadas:
        con.commit()
    return quitadas


def _migrar_respuesta_opcional(con: sqlite3.Connection) -> bool:
    """Deja `respuesta` admitir NULL, si la base viene de cuando era obligatoria.

    UNA NOTA SIN DECISIÓN es una fila con comentario y sin respuesta: «no sé qué decir todavía, pero
    esto conviene mirarlo con alguien». Antes eso no tenía dónde ir —la API pedía las dos cosas
    juntas— así que el texto quedaba en un borrador en memoria y se perdía al recargar la página.

    SQLITE NO SABE QUITAR UN `NOT NULL`. `ALTER TABLE` puede agregar y borrar columnas, no cambiarles
    las restricciones, así que la única forma es recrear la tabla y copiar las filas. Se hace dentro
    de una transacción: si algo sale mal a mitad de camino, la base queda como estaba en vez de a
    medio migrar. Y se recrean los índices, que se van con la tabla vieja.

    Idempotente: pregunta por el `notnull` de la columna antes de tocar nada.
    """
    fila = next((f for f in con.execute("PRAGMA table_info(clasificaciones)")
                 if f["name"] == "respuesta"), None)
    if fila is None or not fila["notnull"]:
        return False
    with _lock:
        con.executescript("""
            BEGIN;
            CREATE TABLE clasificaciones_nueva (
                nodo          TEXT NOT NULL,
                event_id      INTEGER NOT NULL,
                usuario       TEXT NOT NULL,
                respuesta     TEXT,
                comentario    TEXT NOT NULL DEFAULT '',
                creado_en     TEXT NOT NULL,
                actualizado_en TEXT NOT NULL,
                PRIMARY KEY (nodo, event_id, usuario)
            );
            INSERT INTO clasificaciones_nueva
                (nodo, event_id, usuario, respuesta, comentario, creado_en, actualizado_en)
              SELECT nodo, event_id, usuario, respuesta, comentario, creado_en, actualizado_en
                FROM clasificaciones;
            DROP TABLE clasificaciones;
            ALTER TABLE clasificaciones_nueva RENAME TO clasificaciones;
            CREATE INDEX IF NOT EXISTS idx_clas_nodo    ON clasificaciones(nodo);
            CREATE INDEX IF NOT EXISTS idx_clas_usuario ON clasificaciones(usuario);
            COMMIT;
        """)
    return True


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
    _migrar(_con)
    _migrar_respuesta_opcional(_con)
    return _con


def conexion() -> sqlite3.Connection:
    return _con if _con is not None else preparar()


def guardar(
    nodo: str,
    event_id: int,
    usuario: str,
    respuesta: str | None,
    comentario: str = "",
) -> dict:
    """Registra (o corrige) lo que una persona anotó sobre un evento.

    Cambiar de opinión pisa la respuesta anterior pero **conserva `creado_en`**: interesa cuándo se
    miró el evento por primera vez, no solo la última corrección.

    `respuesta` PUEDE SER `None`: es una nota sin decisión, y hace falta que exista. Quien mira un
    evento y no sabe todavía qué contestar igual quiere poder anotar «esto conviene verlo con
    alguien»; antes ese texto no tenía dónde ir y se perdía al recargar la página. Lo que no se
    acepta es una fila vacía —ni respuesta ni comentario—, que no sería un registro de nada.

    Una nota NO es una decisión, y eso vale para las cuentas: `resumen_nodo` la deja afuera. Ver ahí
    por qué, que es el mismo motivo por el que la escala no tiene opción premarcada.
    """
    if respuesta is not None and respuesta not in CODIGOS:
        raise ValueError(f"Respuesta desconocida: {respuesta!r}")
    comentario = (comentario or "").strip()[:MAX_COMENTARIO]
    if respuesta is None and not comentario:
        raise ValueError("Hace falta una respuesta o un comentario")
    ahora = _ahora()
    con = conexion()
    with _lock:
        con.execute(
            """INSERT INTO clasificaciones
                 (nodo, event_id, usuario, respuesta, comentario, creado_en, actualizado_en)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(nodo, event_id, usuario) DO UPDATE SET
                 respuesta = excluded.respuesta,
                 comentario = excluded.comentario,
                 actualizado_en = excluded.actualizado_en""",
            (nodo, int(event_id), usuario, respuesta, comentario, ahora, ahora),
        )
        con.commit()
    return mia(nodo, int(event_id), usuario) or {}


def retirar(nodo: str, event_id: int, usuario: str) -> bool:
    """Quita mi respuesta sobre un evento. Devuelve si había algo que quitar.

    BORRA LA FILA, y eso merece justificación porque el resto del módulo está construido sobre lo
    contrario: borrar una rama conserva las clasificaciones, dar de baja una cuenta también. Esas
    dos protegen contra un borrado COLATERAL —nadie eligió deshacerse de esos juicios—. Acá la
    persona que emitió el juicio decide retirarlo, que es la única mano con derecho a hacerlo: la
    clave primaria incluye al usuario, así que nadie puede retirar lo de otro.

    Y borrar del todo, en vez de marcar la fila como retirada, para que «sin clasificar» siga
    siendo UN SOLO estado. Con una fila retirada habría dos maneras de no tener respuesta, y las
    seis consultas del módulo tendrían que acordarse de distinguirlas para siempre; la primera que
    se olvidara contaría como respondido un evento que nadie respondió. Tampoco hay incoherencia
    con lo que ya hacía `guardar`: corregir un voto pisa el anterior sin dejar rastro, así que el
    módulo nunca prometió historial. Si algún día hace falta, el lugar es una bitácora aparte que
    registre las tres acciones —alta, corrección y retiro—, no media promesa acá.

    No es idempotente por accidente: devuelve `False` si no había fila, y con eso la API puede
    responder 404 en vez de fingir que retiró algo.
    """
    con = conexion()
    with _lock:
        cur = con.execute(
            "DELETE FROM clasificaciones WHERE nodo = ? AND event_id = ? AND usuario = ?",
            (nodo, int(event_id), usuario),
        )
        con.commit()
    return cur.rowcount > 0


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
    """Cuántas DECISIONES hay en una rama y cómo se reparten. Para el encabezado de la tabla.

    Las notas sin decisión (`respuesta IS NULL`) quedan afuera del reparto y del total, y se cuentan
    aparte en `notas`. Mezclarlas sería el mismo error que premarcar «Neutral» en la escala: haría
    indistinguible «no se pronunció» de «se pronunció así», que es justo lo que la Etapa 2 necesita
    poder separar. `revisores` sí las cuenta: alguien que dejó una nota participó.
    """
    filas = conexion().execute(
        """SELECT respuesta, COUNT(*) AS n
           FROM clasificaciones WHERE nodo = ? AND respuesta IS NOT NULL GROUP BY respuesta""",
        (nodo,),
    ).fetchall()
    reparto = {f["respuesta"]: int(f["n"]) for f in filas}
    otros = conexion().execute(
        """SELECT COUNT(DISTINCT usuario) AS revisores,
                  SUM(CASE WHEN respuesta IS NULL THEN 1 ELSE 0 END) AS notas
             FROM clasificaciones WHERE nodo = ?""",
        (nodo,),
    ).fetchone()
    return {
        "total": sum(reparto.values()),
        "reparto": reparto,
        "revisores": int(otros["revisores"]),
        "notas": int(otros["notas"] or 0),
    }


def catalogado() -> dict[str, dict]:
    """Todo lo clasificado, agrupado por rama y evento. Para el catálogo de la Etapa 2.5.

    Devuelve `{nodo: {event_id: [{usuario, respuesta, comentario, …}, …]}}`, con nombre y todo.

    EL CIEGO NO SE PROTEGE ACÁ, se protege por rol. Esta función es la única del módulo que expone
    quién dijo qué, y por eso su único consumidor es un endpoint cerrado al administrador: el
    catálogo es la Etapa 2.5, que empieza cuando la clasificación ya se hizo, y quien la mira no es
    ninguno de los revisores cuya independencia hay que preservar.

    Hubo una versión que devolvía «lo mío completo y de los demás solo el reparto sin nombres», para
    que un revisor pudiera ver el conjunto sin romper el ciego. Se descartó al separar las etapas:
    un filtro que hay que acordarse de aplicar bien en cada consulta es más frágil que una pantalla
    a la que el revisor no entra. El precedente es `de_evento`, que existe desde el principio y
    ningún endpoint usaba, justamente por este miedo.

    NO TRAE HOJA NI RANGO. Eso sale del entregable de la rama, que es su única fuente; ver en el
    encabezado por qué la copia dentro de la fila se quitó.
    """
    filas = conexion().execute(
        """SELECT nodo, event_id, usuario, respuesta, comentario, creado_en, actualizado_en
             FROM clasificaciones ORDER BY nodo, event_id, usuario"""
    ).fetchall()
    por_nodo: dict[str, dict] = {}
    for f in filas:
        por_nodo.setdefault(f["nodo"], {}).setdefault(f["event_id"], []).append(dict(f))
    return por_nodo


def revisores() -> list[str]:
    """Quiénes clasificaron algo, alguna vez. Para las columnas del catálogo."""
    return [f["usuario"] for f in conexion().execute(
        "SELECT DISTINCT usuario FROM clasificaciones ORDER BY usuario")]


def borrar_de(nodos: list[str]) -> int:
    """Borra las clasificaciones de esas ramas. Devuelve cuántas se fueron.

    LA PAREJA DE `cuantas_en`: esa cuenta lo que se perdería, esta lo pierde. Se usan juntas al
    borrar una rama —primero para avisar, después para ejecutar— y por eso viven al lado.

    ANTES ESTAS FILAS SOBREVIVÍAN A SU RAMA, y era una promesa a medias. La fila quedaba, pero la
    única forma de volver a ella era su `nodo`, un hash de 16 caracteres que desaparecía del árbol
    justo al borrarlo: no había listado de huérfanas ni pantalla que las mostrara —a diferencia de
    `revision.py`, que sí tiene las dos cosas para sus documentos—. El dato se conservaba y era
    inalcanzable salvo abriendo el SQLite a mano.

    Entre construir esa mitad que faltaba o borrar de verdad, se eligió borrar: el juicio pertenece
    a la corrida donde se emitió —ver «Es por rama» en el encabezado— así que sin la rama no es un
    juicio recuperable, es una opinión sobre un identificador que ya no resuelve a nada. Lo que
    protege el trabajo es el aviso ANTES: `delete_nodo` se planta con 409 y exige `forzar`, y ahora
    el aviso dice cuántas clasificaciones se van, que es lo que antes no decía.
    """
    if not nodos:
        return 0
    marcas = ",".join("?" * len(nodos))
    con = conexion()
    with _lock:
        cur = con.execute(f"DELETE FROM clasificaciones WHERE nodo IN ({marcas})", nodos)
        con.commit()
    return cur.rowcount


def cuantas_en(nodos: list[str]) -> int:
    """Cuántas filas cuelgan de un conjunto de ramas: decisiones Y notas sin decisión.

    La usa el borrado en cascada para poder avisar antes de llevarse por delante trabajo humano,
    igual que ya hace con los documentos de revisión. Por eso cuenta las notas: una nota es texto
    que alguien escribió y que el borrado se va a llevar, así que tiene que estar en el aviso. Es
    la diferencia con `resumen_nodo`, que mide juicios y las deja afuera — acá la pregunta no es
    «cuánto se juzgó» sino «cuánto se pierde».
    """
    if not nodos:
        return 0
    marcas = ",".join("?" * len(nodos))
    fila = conexion().execute(
        f"SELECT COUNT(*) AS n FROM clasificaciones WHERE nodo IN ({marcas})", nodos
    ).fetchone()
    return int(fila["n"])

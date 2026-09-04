"""Cuentas y sesiones: quién entra al taller y quién firma cada juicio.

Hasta acá el taller no tenía usuarios. Eso alcanzaba mientras corría en una máquina de escritorio,
pero deja de alcanzar por dos motivos distintos que conviene no confundir:

1. **Proteger los datos.** La telemetría del satélite y los resultados de las corridas no son
   públicos. Cualquiera que llegara al puerto podía verlos, lanzar ejecuciones y borrar ramas.

2. **Atribuir el juicio.** La clasificación de eventos (`clasificacion.py`) es la opinión de una
   persona sobre telemetría que nadie etiquetó. Sin identidad no hay a quién atribuirla, y dos
   revisores se pisarían la respuesta. La autenticación no es acá solo una reja: es lo que hace
   posible que la Etapa 2 tenga varios revisores independientes.

**Dónde vive.** En `data/revision/`, junto a los documentos del experto, y NO en `ejecuciones.sqlite`.
El árbol de ramas es desechable —`mise run limpiar` lo borra entero y está bien, porque se
recalcula—; las cuentas no. Es el mismo criterio que ya sigue `revision.py`, por la misma razón.

**El superadministrador sale del `.env`, no de la base.** `ADMIN_USUARIO`/`ADMIN_CONTRASENA` se
siembran en cada arranque. Es deliberado: si alguien se queda afuera, o la base se pierde, o hay que
levantar el taller en un servidor nuevo, se edita un archivo y se reinicia. Un administrador que
solo existiera adentro de la base sería un candado sin copia de la llave.

**Qué NO cubre esto.** Los websockets del proxy de OnlyOffice no pasan por el middleware HTTP de
Starlette, así que quedan fuera de la sesión. Es un hueco angosto —hace falta la clave de un
documento, que solo se entrega a quien ya está autenticado— pero está, y se declara acá en lugar de
dejarlo implícito.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import ajustes

#: Misma carpeta que los documentos del experto: lo que no se recalcula viaja junto, y respaldar
#: sigue siendo copiar `data/revision/`.
DIR_CUENTAS: Path = ajustes.DIR_DATOS / "revision"

#: Base propia, separada de `ejecuciones.sqlite` (desechable) y de `revision.sqlite` (documentos).
BASE: Path = DIR_CUENTAS / "cuentas.sqlite"

#: Nombre de la cookie de sesión.
COOKIE = "sesion_taller"

#: Roles. `admin` administra usuarios; `revisor` entra y clasifica.
ADMIN, REVISOR = "admin", "revisor"

# Parámetros de scrypt. 128 · N · r ≈ 16 MB por verificación: caro para quien prueba contraseñas al
# por mayor, imperceptible para quien entra una vez al día.
_SCRYPT_N, _SCRYPT_R, _SCRYPT_P, _SCRYPT_LEN = 2**14, 8, 1, 32
_SCRYPT_MAXMEM = 64 * 1024 * 1024

_lock = threading.Lock()
_con: sqlite3.Connection | None = None

ESQUEMA = """
CREATE TABLE IF NOT EXISTS usuarios (
    nombre         TEXT PRIMARY KEY,
    clave          TEXT NOT NULL,
    rol            TEXT NOT NULL DEFAULT 'revisor',
    creado_en      TEXT NOT NULL,
    creado_por     TEXT,
    ultimo_ingreso TEXT
);

CREATE TABLE IF NOT EXISTS sesiones (
    testigo   TEXT PRIMARY KEY,
    usuario   TEXT NOT NULL,
    creada_en TEXT NOT NULL,
    expira_en TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sesiones_usuario ON sesiones(usuario);
"""


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


def _iso(momento: datetime) -> str:
    return momento.isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------
# Base
# --------------------------------------------------------------------------------------

def preparar() -> sqlite3.Connection:
    """Abre la base, crea las tablas y siembra el administrador del `.env`."""
    global _con
    if _con is not None:
        return _con
    DIR_CUENTAS.mkdir(parents=True, exist_ok=True)
    _con = sqlite3.connect(BASE, check_same_thread=False)
    _con.row_factory = sqlite3.Row
    _con.executescript(ESQUEMA)
    _sembrar_admin(_con)
    return _con


def conexion() -> sqlite3.Connection:
    return _con if _con is not None else preparar()


def _sembrar_admin(con: sqlite3.Connection) -> None:
    """Crea o actualiza el administrador definido en el `.env`.

    Corre en CADA arranque, no solo la primera vez, y eso es lo que lo hace útil: cambiar
    `ADMIN_CONTRASENA` y reiniciar es la forma de recuperar el acceso sin tocar la base a mano.

    Si las variables están vacías no se toca nada: el taller arranca igual y lo avisa en
    `/api/estado`, en vez de inventar un usuario con una contraseña por defecto — que sería la peor
    de las tres opciones, porque parecería seguro sin serlo.
    """
    nombre = (os.environ.get("ADMIN_USUARIO", "") or "").strip()
    clave = os.environ.get("ADMIN_CONTRASENA", "") or ""
    if not nombre or not clave:
        return
    with _lock:
        con.execute(
            """INSERT INTO usuarios (nombre, clave, rol, creado_en, creado_por)
               VALUES (?, ?, ?, ?, '.env')
               ON CONFLICT(nombre) DO UPDATE SET clave = excluded.clave, rol = excluded.rol""",
            (nombre, hashear(clave), ADMIN, _iso(_ahora())),
        )
        con.commit()


def hay_admin() -> bool:
    """¿Existe al menos un administrador? Si no, nadie puede dar de alta usuarios."""
    fila = conexion().execute(
        "SELECT COUNT(*) AS n FROM usuarios WHERE rol = ?", (ADMIN,)
    ).fetchone()
    return bool(fila["n"])


# --------------------------------------------------------------------------------------
# Contraseñas
# --------------------------------------------------------------------------------------

def hashear(clave: str) -> str:
    """`scrypt$N$r$p$sal$hash`, todo en hexadecimal.

    Los parámetros viajan pegados al hash para poder subirlos más adelante sin invalidar las
    contraseñas ya guardadas: cada fila dice con qué costo se calculó.
    """
    sal = secrets.token_bytes(16)
    bruto = hashlib.scrypt(
        clave.encode("utf-8"), salt=sal, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=_SCRYPT_LEN, maxmem=_SCRYPT_MAXMEM,
    )
    return f"scrypt${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${sal.hex()}${bruto.hex()}"


def verificar(clave: str, guardado: str) -> bool:
    """Compara en tiempo constante.

    Un `guardado` con formato raro devuelve `False`, no una excepción: una fila corrupta no tiene
    por qué tumbarle el ingreso a todo el mundo.
    """
    try:
        etiqueta, n, r, p, sal_hex, hash_hex = guardado.split("$")
        if etiqueta != "scrypt":
            return False
        bruto = hashlib.scrypt(
            clave.encode("utf-8"), salt=bytes.fromhex(sal_hex),
            n=int(n), r=int(r), p=int(p), dklen=len(hash_hex) // 2, maxmem=_SCRYPT_MAXMEM,
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(bruto.hex(), hash_hex)


# --------------------------------------------------------------------------------------
# Usuarios
# --------------------------------------------------------------------------------------

def obtener(nombre: str) -> dict | None:
    fila = conexion().execute("SELECT * FROM usuarios WHERE nombre = ?", (nombre,)).fetchone()
    return dict(fila) if fila is not None else None


def listar() -> list[dict]:
    """Los usuarios, sin el hash de la contraseña: esto se sirve por la API."""
    filas = conexion().execute(
        "SELECT nombre, rol, creado_en, creado_por, ultimo_ingreso FROM usuarios ORDER BY nombre"
    ).fetchall()
    return [dict(f) for f in filas]


def crear(nombre: str, clave: str, *, rol: str = REVISOR, creado_por: str | None = None) -> dict:
    """Alta de usuario. Lanza `ValueError` con un motivo legible si el alta no es válida."""
    nombre = (nombre or "").strip()
    if not nombre:
        raise ValueError("El nombre de usuario no puede estar vacío")
    if len(nombre) > 40 or not all(c.isalnum() or c in "._-" for c in nombre):
        raise ValueError("El nombre admite letras, números, punto, guion y guion bajo (hasta 40)")
    if len(clave or "") < 8:
        raise ValueError("La contraseña tiene que tener al menos 8 caracteres")
    if rol not in (ADMIN, REVISOR):
        raise ValueError(f"Rol desconocido: {rol}")
    if obtener(nombre) is not None:
        raise ValueError(f"Ya existe un usuario llamado {nombre!r}")
    con = conexion()
    with _lock:
        con.execute(
            "INSERT INTO usuarios (nombre, clave, rol, creado_en, creado_por) VALUES (?, ?, ?, ?, ?)",
            (nombre, hashear(clave), rol, _iso(_ahora()), creado_por),
        )
        con.commit()
    return {"nombre": nombre, "rol": rol}


def cambiar_clave(nombre: str, clave: str) -> None:
    """Cambia la contraseña y **cierra las sesiones abiertas** de esa persona.

    Si se la cambia porque se filtró, dejar vivas las sesiones haría que el cambio no sirviera
    de nada: quien tuviera la cookie seguiría adentro.
    """
    if len(clave or "") < 8:
        raise ValueError("La contraseña tiene que tener al menos 8 caracteres")
    if obtener(nombre) is None:
        raise ValueError(f"No existe el usuario {nombre!r}")
    con = conexion()
    with _lock:
        con.execute("UPDATE usuarios SET clave = ? WHERE nombre = ?", (hashear(clave), nombre))
        con.execute("DELETE FROM sesiones WHERE usuario = ?", (nombre,))
        con.commit()


def borrar(nombre: str) -> None:
    """Baja de usuario.

    **No borra sus clasificaciones**: son juicio humano y sobreviven a la cuenta, igual que un
    documento de revisión sobrevive a la rama que lo originó. Quedan atribuidas al nombre.
    """
    con = conexion()
    with _lock:
        con.execute("DELETE FROM usuarios WHERE nombre = ?", (nombre,))
        con.execute("DELETE FROM sesiones WHERE usuario = ?", (nombre,))
        con.commit()


# --------------------------------------------------------------------------------------
# Sesiones
# --------------------------------------------------------------------------------------

def _huella(testigo: str) -> str:
    """Lo que se guarda en la base es el hash del testigo, no el testigo.

    La cookie es el secreto; la base es una lista de secretos que alguien podría llegar a leer.
    Guardando el hash, una copia de `cuentas.sqlite` no alcanza para hacerse pasar por nadie.
    """
    return hashlib.sha256(testigo.encode("utf-8")).hexdigest()


def autenticar(nombre: str, clave: str) -> dict | None:
    """El usuario si las credenciales son correctas, `None` si no.

    Verifica el hash **incluso cuando el usuario no existe**, contra un valor de descarte. Sin eso,
    un nombre inexistente contestaría en microsegundos y uno existente en decenas de milisegundos:
    esa diferencia alcanza para enumerar quién tiene cuenta.
    """
    usuario = obtener(nombre)
    guardado = usuario["clave"] if usuario else hashear("descarte")
    ok = verificar(clave, guardado)
    return usuario if (usuario and ok) else None


def abrir_sesion(nombre: str, *, dias: int | None = None) -> str:
    """Crea una sesión y devuelve el testigo que va en la cookie.

    Es la única vez que el testigo existe en claro: de acá en más solo se guarda su hash.
    """
    testigo = secrets.token_urlsafe(32)
    ahora = _ahora()
    vence = ahora + timedelta(days=dias if dias is not None else ajustes.SESION_DIAS)
    con = conexion()
    with _lock:
        con.execute(
            "INSERT INTO sesiones (testigo, usuario, creada_en, expira_en) VALUES (?, ?, ?, ?)",
            (_huella(testigo), nombre, _iso(ahora), _iso(vence)),
        )
        con.execute("UPDATE usuarios SET ultimo_ingreso = ? WHERE nombre = ?", (_iso(ahora), nombre))
        con.commit()
    return testigo


def usuario_de(testigo: str | None) -> dict | None:
    """El usuario de una sesión válida, o `None`. Aprovecha para descartar la sesión si venció."""
    if not testigo:
        return None
    fila = conexion().execute(
        "SELECT usuario, expira_en FROM sesiones WHERE testigo = ?", (_huella(testigo),)
    ).fetchone()
    if fila is None:
        return None
    if fila["expira_en"] < _iso(_ahora()):
        cerrar_sesion(testigo)
        return None
    usuario = obtener(fila["usuario"])
    if usuario is None:  # la cuenta se borró con la sesión abierta
        cerrar_sesion(testigo)
        return None
    return {"nombre": usuario["nombre"], "rol": usuario["rol"]}


def cerrar_sesion(testigo: str | None) -> None:
    if not testigo:
        return
    con = conexion()
    with _lock:
        con.execute("DELETE FROM sesiones WHERE testigo = ?", (_huella(testigo),))
        con.commit()


def purgar_vencidas() -> int:
    con = conexion()
    with _lock:
        cur = con.execute("DELETE FROM sesiones WHERE expira_en < ?", (_iso(_ahora()),))
        con.commit()
    return cur.rowcount


# --------------------------------------------------------------------------------------
# Freno a la fuerza bruta
# --------------------------------------------------------------------------------------
# En memoria y por proceso, a propósito: no hace falta más para un taller de laboratorio, y una
# tabla en la base convertiría cada intento fallido en una escritura. Lo que sí hace falta es que
# probar contraseñas al por mayor no salga gratis.

_INTENTOS: dict[str, list[float]] = {}
_MAX_INTENTOS, _VENTANA_S = 8, 300.0


def freno(clave_intento: str, ahora: float) -> float:
    """Segundos que faltan para poder volver a intentar. 0 = adelante."""
    recientes = [t for t in _INTENTOS.get(clave_intento, []) if ahora - t < _VENTANA_S]
    if recientes:
        _INTENTOS[clave_intento] = recientes
    else:
        _INTENTOS.pop(clave_intento, None)
    if len(recientes) < _MAX_INTENTOS:
        return 0.0
    return round(_VENTANA_S - (ahora - recientes[0]), 1)


def anotar_fallo(clave_intento: str, ahora: float) -> None:
    _INTENTOS.setdefault(clave_intento, []).append(ahora)


def limpiar_fallos(clave_intento: str) -> None:
    _INTENTOS.pop(clave_intento, None)

"""Sin cuenta se mira todo; sin cuenta no se escribe nada.

POR QUÉ EXISTE. El taller dejó de pedir sesión para entrar: un tutor o un tribunal pueden ver los
resultados sin que haya que darles de alta. La sesión pasó a habilitar **escribir**. Eso mueve la
frontera de seguridad de «hay reja» a «la reja distingue leer de escribir», y una frontera que
distingue es una frontera que se puede equivocar en dos direcciones:

  · de más — un endpoint de escritura que quedó abierto y cualquiera puede borrar una rama;
  · de menos — una lectura que quedó cerrada y el modo lectura muestra una pantalla rota.

Las dos son silenciosas. La primera no falla nunca hasta que alguien la usa; la segunda falla en
el navegador de un visitante que no va a reportarla. Por eso la lista de abajo es exhaustiva y no
un par de casos de muestra.

CÓMO ESTÁ ESCRITO. Se prueba `_necesita_sesion` directamente y además por HTTP. Lo primero es
barato y cubre muchas rutas; lo segundo es lo que de verdad importa, porque afirma que el
middleware está montado y que la regla que se probó es la que corre.
"""

import importlib

import pytest

from conftest import olvidar_backend

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def taller(tmp_path, monkeypatch):
    """Un taller vacío con un administrador conocido. Mismo montaje que `test_cuentas`."""
    monkeypatch.setenv("DIR_DATOS", str(tmp_path))
    monkeypatch.setenv("ADMIN_USUARIO", "jefa")
    monkeypatch.setenv("ADMIN_CONTRASENA", "contrasena-larga")
    monkeypatch.setenv("OO_URL_INTERNA", "")
    monkeypatch.setenv("OO_URL_DEL_TALLER", "")
    # La cookie SIN `Secure`, aunque el servidor donde corran los tests la tenga encendida.
    # `TestClient` habla http contra `http://testserver`, y una cookie `Secure` no viaja por http:
    # el ingreso devolvía 200 y la petición siguiente llegaba sin sesión — exactamente el modo de
    # falla que `.env.example` advierte para el navegador, reproducido en la suite.
    #
    # Sin fijarlo, los tests dependen del `.env` de la máquina donde corren: pasaban en la de
    # desarrollo (COOKIE_SEGURA=0) y fallaban en el servidor (=1). Un test que cambia de resultado
    # según la configuración del ambiente no afirma nada sobre el código.
    monkeypatch.setenv("COOKIE_SEGURA", "0")

    olvidar_backend()
    ajustes = importlib.import_module("backend.ajustes")
    assert ajustes.DIR_DATOS == tmp_path, "el test escribiría en la carpeta de datos real"
    main = importlib.import_module("backend.main")

    with TestClient(main.app) as cliente:
        yield cliente, main

    olvidar_backend()


#: Todo lo que un visitante sin cuenta tiene que poder pedir. Si algo de acá empieza a dar 401, el
#: modo lectura queda a medias y nadie se entera hasta que alguien mira desde afuera.
ABIERTAS = [
    ("GET", "/"),
    ("GET", "/taller"),
    ("GET", "/login"),
    ("GET", "/estatico/estilos.css"),
    ("GET", "/api/salud"),
    ("GET", "/api/acceso"),
    ("GET", "/api/estado"),
    ("GET", "/api/etapas"),
    ("GET", "/api/arbol"),
    ("GET", "/api/nodo/loquesea"),
    ("GET", "/api/nodo/loquesea/datos"),
    ("GET", "/api/nodo/loquesea/analisis"),
    ("GET", "/api/nodo/loquesea/evento/1"),
    ("GET", "/api/nodo/loquesea/excel/experto"),
]

#: Todo lo que NO. Escribir, las cuentas, la revisión experta y lo que responde «mi juicio».
CERRADAS = [
    ("POST", "/api/ejecutar"),
    ("DELETE", "/api/nodo/loquesea"),
    ("PUT", "/api/nodo/loquesea/etiqueta"),
    ("PUT", "/api/nodo/loquesea/evento/1/clasificacion"),
    ("DELETE", "/api/nodo/loquesea/evento/1/clasificacion"),
    ("GET", "/api/nodo/loquesea/clasificacion"),
    ("GET", "/api/nodo/loquesea/evento/1/clasificacion"),
    ("POST", "/api/nodo/loquesea/revision/experto"),
    ("GET", "/api/yo"),
    ("GET", "/api/usuarios"),
    ("POST", "/api/usuarios"),
    ("GET", "/api/revision"),
    ("GET", "/api/revision/loquesea/editor"),
    ("GET", "/usuarios"),
    ("GET", "/revision"),
]


@pytest.mark.parametrize("metodo,ruta", ABIERTAS)
def test_lo_que_se_puede_ver_sin_cuenta(taller, metodo, ruta):
    """No pide sesión. El código puede ser 200 o 404 —el árbol está vacío—, nunca 401 ni 303."""
    cliente, _ = taller
    r = cliente.request(metodo, ruta, follow_redirects=False)
    assert r.status_code not in (401, 303), f"{metodo} {ruta} pide sesión y no debería"


@pytest.mark.parametrize("metodo,ruta", CERRADAS)
def test_lo_que_no_se_puede_hacer_sin_cuenta(taller, metodo, ruta):
    """Pide sesión: 401 para la API, 303 al ingreso para una navegación."""
    cliente, _ = taller
    r = cliente.request(metodo, ruta, json={}, follow_redirects=False)
    esperado = (303,) if not ruta.startswith("/api/") else (401,)
    assert r.status_code in esperado, f"{metodo} {ruta} dio {r.status_code} sin sesión"


def test_un_metodo_de_escritura_nuevo_nace_cerrado(taller):
    """La regla es por método, y esto lo fija.

    Es la propiedad que hace que la frontera aguante el paso del tiempo: alguien agrega mañana un
    `POST /api/loquesea` y nace pidiendo sesión sin acordarse de tocar la lista. Si esto se rompe,
    es que alguien invirtió la regla y volvió a una lista blanca de rutas — que falla al revés.
    """
    _, main = taller
    for metodo in ("POST", "PUT", "PATCH", "DELETE"):
        assert main._necesita_sesion(metodo, "/api/algo/que/todavia/no/existe"), metodo


def test_el_ingreso_y_la_salida_siguen_abiertos(taller):
    """Las dos escrituras que no pueden pedir sesión: la que la crea y la que la cierra."""
    _, main = taller
    assert not main._necesita_sesion("POST", "/api/sesion")
    assert not main._necesita_sesion("POST", "/api/sesion/salir")


def test_las_dos_rutas_del_document_server_siguen_abiertas(taller):
    """El callback es un POST y tiene que seguir pasando: su llave es la ficha, no la sesión.

    Ya lo afirma `test_cuentas`, pero se repite acá porque la regla que las deja pasar es otra
    ahora —la primera condición de `_necesita_sesion`— y romperla desde este lado no lo detectaría
    aquel test hasta que alguien mirara por qué la revisión experta dejó de guardar.
    """
    cliente, _ = taller
    assert cliente.get("/api/revision/inexistente/archivo").status_code != 401
    assert cliente.post("/api/revision/inexistente/callback", json={}).status_code != 401


def test_el_estado_dice_quien_mira(taller):
    """`/api/estado` es de donde el frontend saca si dibuja o no los controles de escritura.

    Sin sesión tiene que decir `usuario: None` y no fallar: si tirara 401, el taller no cargaría
    para un visitante, que es justo lo que este cambio quiere permitir.
    """
    cliente, _ = taller
    r = cliente.get("/api/estado")
    assert r.status_code == 200
    assert r.json()["usuario"] is None

    cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    assert cliente.get("/api/estado").json()["usuario"]["nombre"] == "jefa"

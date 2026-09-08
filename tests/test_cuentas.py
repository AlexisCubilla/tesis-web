"""Cuentas, sesiones y la reja que las usa.

Lo que se afirma acá es lo que no se puede comprobar mirando: que las contraseñas no se guarden en
claro, que las dos rutas del Document Server sigan abiertas (romperlas deja la revisión experta
muerta de una forma que no se parece a su causa), y que todo lo demás esté cerrado.
"""

import importlib

import pytest

from conftest import olvidar_backend

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def taller(tmp_path, monkeypatch):
    """Un taller con estado propio y un administrador conocido.

    Se reimporta el backend entero porque `ajustes` resuelve las rutas y `cuentas` abre su base al
    importarse: sin eso, los tests escribirían en la carpeta `data/` real del repo. Ver
    `conftest.olvidar_backend` para por qué no alcanza con sacar los submódulos de `sys.modules`.
    """
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
    cuentas = importlib.import_module("backend.cuentas")
    assert main.cuentas is cuentas, "main y el test hablarían con bases distintas"

    with TestClient(main.app) as cliente:
        yield cliente, cuentas

    olvidar_backend()


# ---------------------------------------------------------------- contraseñas

def test_la_contrasena_no_se_guarda_en_claro(taller):
    _, cuentas = taller
    guardado = cuentas.obtener("jefa")["clave"]
    assert "contrasena-larga" not in guardado
    assert guardado.startswith("scrypt$")


def test_dos_hashes_de_la_misma_contrasena_son_distintos(taller):
    _, cuentas = taller
    # Sal distinta por hash: si fueran iguales, la base delataría quién comparte contraseña.
    assert cuentas.hashear("misma-clave-12") != cuentas.hashear("misma-clave-12")


def test_verificar_acepta_la_correcta_y_rechaza_el_resto(taller):
    _, cuentas = taller
    guardado = cuentas.hashear("la-correcta-1")
    assert cuentas.verificar("la-correcta-1", guardado)
    assert not cuentas.verificar("la-incorrecta", guardado)
    assert not cuentas.verificar("la-correcta-1", "basura-sin-formato")


def test_el_admin_del_entorno_se_siembra(taller):
    _, cuentas = taller
    assert cuentas.hay_admin()
    assert cuentas.obtener("jefa")["rol"] == cuentas.ADMIN


# ---------------------------------------------------------------- la reja

def test_la_api_de_escritura_sin_sesion_contesta_401(taller):
    """Lo que se lee está abierto; lo que escribe, no.

    Antes bastaba con pedir `/api/arbol` para comprobar la reja. Ya no: el taller se puede mirar
    sin cuenta y ese endpoint contesta 200 a propósito. Lo que hay que afirmar ahora es lo otro.
    """
    cliente, _ = taller
    assert cliente.get("/api/arbol").status_code == 200
    assert cliente.post("/api/ejecutar", json={}).status_code == 401
    assert cliente.delete("/api/nodo/loquesea").status_code == 401
    assert cliente.put("/api/nodo/x/evento/1/clasificacion", json={}).status_code == 401


def test_una_navegacion_sin_sesion_redirige_al_ingreso(taller):
    """Las pantallas de cuentas y de revisión siguen mandando al ingreso.

    `/taller` no: se mira sin sesión. Se comprueba de las dos formas para que quede escrito cuál
    es cuál — si algún día `/taller` vuelve a redirigir, este test lo dice.
    """
    cliente, _ = taller
    assert cliente.get("/taller", follow_redirects=False).status_code == 200

    r = cliente.get("/usuarios", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("login")
    # El destino viaja pegado para volver a donde se iba después de entrar.
    assert "destino=usuarios" in r.headers["location"]


def test_la_redireccion_al_ingreso_no_arranca_en_la_raiz(taller):
    """Ni el destino tampoco: los dos tienen que sobrevivir a un prefijo.

    Publicado bajo `https://…/tesis/`, el proxy le saca el prefijo antes de que la petición llegue
    al taller: acá se ve `/taller` y no hay encabezado que cuente el resto. Un `location` que
    empiece con `/` lo resuelve el navegador contra la raíz del dominio, fuera del prefijo, y el
    ingreso contesta 404 — y el destino, si arranca en `/`, hace lo mismo después de entrar.

    El síntoma no se parece a la causa: la página carga bien y el 404 aparece recién al redirigir.
    """
    cliente, _ = taller
    for ruta in ("/usuarios", "/revision?doc=abc"):
        location = cliente.get(ruta, follow_redirects=False).headers["location"]
        assert not location.startswith("/"), f"{ruta} redirige a la raíz: {location}"
        assert "destino=%2F" not in location, f"{ruta} manda un destino absoluto: {location}"


def test_el_ingreso_y_lo_estatico_quedan_abiertos(taller):
    cliente, _ = taller
    assert cliente.get("/login").status_code == 200
    assert cliente.get("/api/acceso").status_code == 200
    assert cliente.get("/estatico/estilos.css").status_code == 200


def test_las_dos_rutas_del_document_server_no_piden_sesion(taller):
    """Si estas piden sesión, la revisión experta deja de funcionar.

    El Document Server corre en otro contenedor y no tiene con qué autenticarse; su llave es la
    ficha del documento. Un 401 acá significaría que alguien las metió detrás de la sesión: lo que
    se espera es 404 (documento inexistente) o 403 (ficha equivocada), nunca 401.
    """
    cliente, _ = taller
    assert cliente.get("/api/revision/inexistente/archivo").status_code != 401
    assert cliente.post("/api/revision/inexistente/callback", json={}).status_code != 401


def test_la_ruta_de_versiones_si_pide_sesion(taller):
    """La pide el navegador, no el Document Server: no hay motivo para dejarla abierta."""
    cliente, _ = taller
    assert cliente.get("/api/revision/inexistente/version/1").status_code == 401


# ---------------------------------------------------------------- sesión

def test_ingreso_y_salida(taller):
    cliente, _ = taller
    assert cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "mala"}).status_code == 401

    r = cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    assert r.status_code == 200
    assert r.json()["usuario"]["rol"] == "admin"
    # `/api/yo` como sonda de sesión: `/api/arbol` ya no sirve para esto, contesta 200 siempre.
    assert cliente.get("/api/yo").status_code == 200

    cliente.post("/api/sesion/salir")
    assert cliente.get("/api/yo").status_code == 401


def test_la_cookie_de_sesion_es_httponly(taller):
    cliente, _ = taller
    r = cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    cookie = r.headers["set-cookie"].lower()
    # Sin HttpOnly, cualquier script inyectado en la página se lleva la sesión.
    assert "httponly" in cookie
    assert "samesite=lax" in cookie


def test_en_la_base_no_queda_el_testigo_sino_su_hash(taller):
    cliente, cuentas = taller
    cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    testigo = cliente.cookies[cuentas.COOKIE]
    guardados = [f["testigo"] for f in cuentas.conexion().execute("SELECT testigo FROM sesiones")]
    assert testigo not in guardados
    assert cuentas._huella(testigo) in guardados


def test_cambiar_la_contrasena_cierra_las_sesiones(taller):
    cliente, cuentas = taller
    cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    assert cliente.get("/api/yo").status_code == 200
    cuentas.cambiar_clave("jefa", "otra-contrasena")
    assert cliente.get("/api/yo").status_code == 401


# ---------------------------------------------------------------- alta y roles

def _entrar(cliente, usuario, clave):
    r = cliente.post("/api/sesion", json={"usuario": usuario, "contrasena": clave})
    assert r.status_code == 200, r.text


def test_el_admin_crea_usuarios_y_el_revisor_no(taller):
    cliente, _ = taller
    _entrar(cliente, "jefa", "contrasena-larga")

    alta = cliente.post("/api/usuarios",
                        json={"nombre": "revisor1", "contrasena": "clave-de-prueba", "rol": "revisor"})
    assert alta.status_code == 200
    cliente.post("/api/sesion/salir")

    _entrar(cliente, "revisor1", "clave-de-prueba")
    assert cliente.get("/api/usuarios").status_code == 403
    assert cliente.post("/api/usuarios",
                        json={"nombre": "otro", "contrasena": "clave-de-prueba"}).status_code == 403


def test_no_se_puede_repetir_el_nombre_ni_usar_una_clave_corta(taller):
    cliente, _ = taller
    _entrar(cliente, "jefa", "contrasena-larga")
    assert cliente.post("/api/usuarios",
                        json={"nombre": "jefa", "contrasena": "clave-de-prueba"}).status_code == 400
    assert cliente.post("/api/usuarios",
                        json={"nombre": "corto", "contrasena": "abc"}).status_code == 400


def test_el_admin_no_puede_borrarse_a_si_mismo(taller):
    cliente, _ = taller
    _entrar(cliente, "jefa", "contrasena-larga")
    # Quedarse sin ningún administrador dejaría el taller sin quien dé de alta a nadie.
    assert cliente.delete("/api/usuarios/jefa").status_code == 400


def test_cada_uno_cambia_su_propia_contrasena_y_no_la_ajena(taller):
    cliente, _ = taller
    _entrar(cliente, "jefa", "contrasena-larga")
    cliente.post("/api/usuarios", json={"nombre": "ana", "contrasena": "clave-de-prueba"})
    cliente.post("/api/usuarios", json={"nombre": "beto", "contrasena": "clave-de-prueba"})
    cliente.post("/api/sesion/salir")

    _entrar(cliente, "ana", "clave-de-prueba")
    assert cliente.post("/api/usuarios/beto/contrasena",
                        json={"contrasena": "clave-nueva-1"}).status_code == 403
    assert cliente.post("/api/usuarios/ana/contrasena",
                        json={"contrasena": "clave-nueva-1"}).status_code == 200


# ------------------------------------------------- retirar la propia clasificación, por la API

def test_retirar_una_clasificacion_que_no_existe_da_404(taller):
    """Con sesión y todo: no hay nada que retirar, y la API lo dice en vez de fingir un éxito.

    Es la mitad del contrato que el front necesita para distinguir «se retiró» de «la pantalla
    estaba mostrando algo que en la base ya no estaba» —otra pestaña, o una rama borrada—. Sin el
    404, las dos situaciones se ven igual desde el navegador.
    """
    cliente, _ = taller
    cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    r = cliente.delete("/api/nodo/nodo-inexistente/evento/1/clasificacion")
    assert r.status_code == 404


def test_retirar_sin_sesion_no_llega_a_la_base(taller):
    """La reja primero: sin sesión no hay un «yo» cuya respuesta retirar."""
    cliente, _ = taller
    r = cliente.delete("/api/nodo/loquesea/evento/1/clasificacion")
    assert r.status_code == 401


# ---------------------------------------------- el catálogo de la Etapa 2.5, por la API

def test_el_catalogo_es_del_administrador(taller):
    """Un revisor recibe 403, no 401: tiene sesión, lo que no tiene es el rol.

    La diferencia importa para el frontend: con 401 mandaría a la pantalla de ingreso —y volvería a
    entrar la misma persona, al mismo 401—; con 403 muestra la explicación de qué es el catálogo.
    """
    cliente, cuentas = taller
    cuentas.crear("revisora", "contrasena-larga", rol="revisor", creado_por="test")

    cliente.post("/api/sesion", json={"usuario": "revisora", "contrasena": "contrasena-larga"})
    assert cliente.get("/api/clasificacion").status_code == 403
    assert cliente.get("/catalogo").status_code == 200, "la pantalla se sirve; la API es la que corta"

    cliente.post("/api/sesion/salir")
    cliente.post("/api/sesion", json={"usuario": "jefa", "contrasena": "contrasena-larga"})
    assert cliente.get("/api/clasificacion").status_code == 200


def test_una_navegacion_sin_rol_no_se_corta(taller):
    """`/catalogo` y `/revision` se sirven a cualquier sesión, y la API de adentro es la que corta.

    Cortar el HTML dejaría al revisor frente a una página de error del servidor, fuera del taller.
    Así llega a la pantalla y ella le explica qué es y dónde clasificar.
    """
    cliente, cuentas = taller
    cuentas.crear("revisora2", "contrasena-larga", rol="revisor", creado_por="test")
    cliente.post("/api/sesion", json={"usuario": "revisora2", "contrasena": "contrasena-larga"})
    for ruta in ("/catalogo", "/revision"):
        assert cliente.get(ruta, follow_redirects=False).status_code == 200, ruta


def test_un_revisor_sigue_clasificando(taller):
    """Lo que el rol NO le quita: la Etapa 2 es su trabajo.

    Da 404 porque la rama no existe en este taller de prueba, y eso es exactamente lo que hay que
    ver: llegó al endpoint. Un 403 significaría que la reja se pasó de largo.
    """
    cliente, cuentas = taller
    cuentas.crear("revisora3", "contrasena-larga", rol="revisor", creado_por="test")
    cliente.post("/api/sesion", json={"usuario": "revisora3", "contrasena": "contrasena-larga"})
    r = cliente.put("/api/nodo/inexistente/evento/1/clasificacion",
                    json={"respuesta": "si", "comentario": ""})
    assert r.status_code == 404
    assert cliente.get("/api/nodo/inexistente/clasificacion").status_code == 200


def test_coincidir_es_caer_del_mismo_lado_no_marcar_la_misma_casilla(taller):
    """La regla del acuerdo, que es la métrica del catálogo.

    «Sí» y «Definitivamente sí» son la misma respuesta a la pregunta con distinta convicción.
    Contarlas como desacuerdo mediría cuánto se parecen las CASILLAS que eligieron dos personas, no
    si coinciden en el juicio — y lo que la Etapa 2 quiere saber es lo segundo.

    «Neutral» vale 0, así que no cae de ningún lado: contra un «sí» son signos distintos y eso es un
    desacuerdo. Es deliberado — quien dijo neutral no acompañó al que dijo sí.
    """
    _, _ = taller
    from backend.main import _acuerdo
    r = lambda *cods: [{"respuesta": c} for c in cods]

    assert _acuerdo(r("si", "si_definitivo")) == "acuerdo"
    assert _acuerdo(r("no", "no_definitivo")) == "acuerdo"
    assert _acuerdo(r("si", "no")) == "desacuerdo"
    assert _acuerdo(r("si_definitivo", "no_definitivo")) == "desacuerdo"
    assert _acuerdo(r("neutral", "si")) == "desacuerdo"
    assert _acuerdo(r("neutral", "neutral")) == "acuerdo"
    assert _acuerdo(r("si", "si", "si_definitivo")) == "acuerdo", "tres revisores también"
    assert _acuerdo(r("si", "si", "no")) == "desacuerdo", "uno que discrepa alcanza"


def test_un_solo_juicio_no_es_acuerdo_ni_desacuerdo(taller):
    """`None`, y no «acuerdo» por defecto.

    Un evento que miró una sola persona no dice nada sobre la coincidencia entre revisores. Contarlo
    en cualquiera de los dos montones ensuciaría la única cifra que la Etapa 2 quiere medir: con
    cuarenta eventos vistos por uno solo y dos por dos, sumarlos daría un 95 % de coincidencia que
    no describe nada.
    """
    _, _ = taller
    from backend.main import _acuerdo
    assert _acuerdo([]) is None
    assert _acuerdo([{"respuesta": "si"}]) is None

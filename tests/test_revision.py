"""Documentos de revisión: que el trabajo del experto no se pierda por accidente, y que se
vaya cuando alguien lo decide.

Estos tests nacieron con `borrar_de`, y por un motivo concreto: hasta entonces `revision.py` no
tenía ninguno, y el módulo pasó de conservar documentos a **borrar archivos del disco**. Las dos
preguntas que hay que poder contestar son cuáles borra y cuáles no toca; una respuesta equivocada
acá se lleva trabajo humano irrepetible y no hay copia de la que volver.
"""

import importlib
import shutil

import pytest

from conftest import olvidar_backend


@pytest.fixture()
def revision(tmp_path, monkeypatch):
    monkeypatch.setenv("DIR_DATOS", str(tmp_path))
    olvidar_backend()
    ajustes = importlib.import_module("backend.ajustes")
    assert ajustes.DIR_DATOS == tmp_path, "el test escribiría en la carpeta de datos real"
    mod = importlib.import_module("backend.revision")
    mod.preparar()
    yield mod
    olvidar_backend()


def _doc(revision, tmp_path, nodo, tipo="experto", editado=False):
    """Un documento de esa rama. Con `editado`, además con un guardado del experto encima."""
    origen = tmp_path / f"entregable-{nodo}-{tipo}.xlsx"
    origen.write_bytes(b"lo que salio del pipeline")
    doc = revision.crear(nodo=nodo, tipo=tipo, nombre=origen.name, origen=origen,
                         commit_tesis="abc1234")
    if editado:
        doc = revision.registrar_guardado(doc["id"], b"con lo que escribio el experto", "la experta")
    return doc


# --- qué se lleva `borrar_de` -----------------------------------------------------------------


def test_borrar_de_se_lleva_el_documento_y_su_archivo(revision, tmp_path):
    doc = _doc(revision, tmp_path, "ramaA", editado=True)
    carpeta = revision._carpeta(doc["id"])
    assert carpeta.exists()

    assert revision.borrar_de(["ramaA"]) == 1
    assert revision.obtener(doc["id"]) is None
    assert not carpeta.exists(), "quedó la carpeta en disco"
    assert revision.versiones(doc["id"]) == []


def test_borrar_de_se_lleva_el_editado_a_diferencia_de_olvidar(revision, tmp_path):
    """La distinción entre las dos: quién decide.

    `olvidar` se niega a tocar un documento con ediciones —la llama `post_revision` al regenerar un
    entregable, donde nadie pidió perder nada—. `borrar_de` corre cuando la rama entera se va por
    decisión de una persona, con el 409 de por medio, y ahí sí se lleva lo editado.
    """
    doc = _doc(revision, tmp_path, "ramaA", editado=True)
    assert doc["version"] == 1

    with pytest.raises(ValueError):
        revision.olvidar(doc["id"])
    assert revision.obtener(doc["id"]) is not None, "olvidar no debe haberlo tocado"

    assert revision.borrar_de(["ramaA"]) == 1
    assert revision.obtener(doc["id"]) is None


def test_borrar_de_no_toca_las_otras_ramas(revision, tmp_path):
    a = _doc(revision, tmp_path, "ramaA", editado=True)
    b = _doc(revision, tmp_path, "ramaB", editado=True)
    assert revision.borrar_de(["ramaA"]) == 1
    assert revision.obtener(a["id"]) is None
    assert revision.obtener(b["id"]) is not None
    assert revision._carpeta(b["id"]).exists()


def test_borrar_de_se_lleva_los_tres_tipos_de_una_rama(revision, tmp_path):
    """Una rama tiene un documento por tipo de entregable, y la cascada se lleva los que haya."""
    for tipo in ("experto", "presentable", "normales"):
        _doc(revision, tmp_path, "ramaA", tipo=tipo, editado=(tipo == "experto"))
    assert revision.borrar_de(["ramaA"]) == 3
    assert revision.listar("ramaA") == []


def test_borrar_de_acepta_la_cascada_entera(revision, tmp_path):
    """`delete_nodo` pasa el nodo y sus descendientes de una vez."""
    for n in ("raiz", "hijo", "nieto"):
        _doc(revision, tmp_path, n, editado=True)
    _doc(revision, tmp_path, "otra", editado=True)
    assert revision.borrar_de(["raiz", "hijo", "nieto"]) == 3
    assert revision.obtener(revision.id_documento("otra", "experto")) is not None


def test_borrar_de_sin_ramas_no_toca_nada(revision, tmp_path):
    """Una lista vacía no puede convertirse en un `DELETE` sin `WHERE`."""
    doc = _doc(revision, tmp_path, "ramaA", editado=True)
    assert revision.borrar_de([]) == 0
    assert revision.obtener(doc["id"]) is not None


def test_borrar_de_de_una_rama_sin_documentos_no_es_un_error(revision):
    assert revision.borrar_de(["rama-que-nunca-tuvo-nada"]) == 0


def test_con_trabajo_del_experto_es_lo_que_el_aviso_muestra(revision, tmp_path):
    """Las dos mitades del 409: esta función dice qué se perdería, `borrar_de` lo pierde.

    Solo cuenta los editados —un documento en v0 es una copia del entregable y se regenera solo—,
    así que el aviso puede nombrar cero documentos y `borrar_de` llevarse dos. Es correcto: lo que
    hay que confirmar es la pérdida de trabajo humano, no la de archivos.
    """
    _doc(revision, tmp_path, "ramaA", tipo="experto", editado=True)
    _doc(revision, tmp_path, "ramaA", tipo="normales", editado=False)

    assert [d["tipo"] for d in revision.con_trabajo_del_experto(["ramaA"])] == ["experto"]
    assert revision.borrar_de(["ramaA"]) == 2


# --- la columna `rama_borrada`, que se fue ----------------------------------------------------


def test_la_migracion_quita_la_columna_vieja_y_conserva_los_documentos(revision, tmp_path):
    """Una base con el esquema anterior tiene que quedar limpia SIN perder documentos.

    `rama_borrada` marcaba los documentos cuya rama se había borrado, cuando eso los dejaba
    huérfanos. Ahora se van con la rama, así que nadie la escribe: nace en 0 y se queda en 0, que es
    la peor clase de columna —parece decir algo y no dice nada—.
    """
    import sqlite3

    doc = _doc(revision, tmp_path, "ramaA", editado=True)
    doc_id = doc["id"]
    con = revision.conexion()
    con.execute("ALTER TABLE documentos ADD COLUMN rama_borrada INTEGER NOT NULL DEFAULT 0")
    con.execute("UPDATE documentos SET rama_borrada=1 WHERE id=?", (doc_id,))
    con.commit()
    assert "rama_borrada" in {f["name"] for f in con.execute("PRAGMA table_info(documentos)")}

    assert revision._migrar(con) is True
    columnas = {f["name"] for f in con.execute("PRAGMA table_info(documentos)")}
    assert "rama_borrada" not in columnas

    vivo = revision.obtener(doc_id)
    assert vivo["version"] == 1
    assert vivo["ultimo_autor"] == "la experta"
    assert revision.ruta_actual(doc_id).read_bytes() == b"con lo que escribio el experto"


def test_la_migracion_no_se_queja_en_una_base_ya_migrada(revision):
    """Corre en cada arranque, así que tiene que ser idempotente."""
    con = revision.conexion()
    assert revision._migrar(con) is False
    assert revision._migrar(con) is False


# --- recrear la misma rama --------------------------------------------------------------------


def test_recrear_la_misma_rama_ya_no_encuentra_el_documento_viejo(revision, tmp_path):
    """El escenario que motivó el cambio, ahora sin la mitad rara.

    La clave de un nodo es un hash de (etapa, parámetros, padre), así que recrear una rama con los
    mismos parámetros da la misma clave y el mismo `doc_id`. Cuando el documento sobrevivía, se
    reconectaba solo —eso funcionaba— pero quedaba marcado como huérfano para siempre, porque nada
    devolvía esa columna a cero: la pantalla anunciaba «la rama de este documento se borró» sobre
    una rama viva.

    Ahora el documento se fue con la rama, así que recrearla parte de cero. Se pierde el trabajo del
    experto —el 409 lo avisa antes— y a cambio no hay ningún estado a medio camino.
    """
    doc = _doc(revision, tmp_path, "ramaA", editado=True)
    doc_id = doc["id"]
    revision.borrar_de(["ramaA"])

    assert revision.obtener(doc_id) is None
    assert revision.id_documento("ramaA", "experto") == doc_id, "la clave sigue siendo estable"

    nuevo = _doc(revision, tmp_path, "ramaA", editado=False)
    assert nuevo["id"] == doc_id
    assert nuevo["version"] == 0, "arranca de cero, sin arrastrar la versión del anterior"
    assert revision.ruta_actual(doc_id).read_bytes() == b"lo que salio del pipeline"
    assert [v["version"] for v in revision.versiones(doc_id)] == [0]

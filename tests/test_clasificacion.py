"""La encuesta de eventos: que sea por persona, que se pueda corregir y que se pueda deshacer.

Estos tests van contra el módulo, sin levantar el pipeline: lo que hay que afirmar acá es el
contrato de almacenamiento, no que los eventos existan. Que la respuesta de una persona no se mezcle
con la de otra es un requisito del método —la coincidencia entre revisores independientes es lo que
se quiere medir en la Etapa 2— y no algo que se pueda comprobar mirando la pantalla.
"""

import importlib

import pytest

from conftest import olvidar_backend


@pytest.fixture()
def clasificacion(tmp_path, monkeypatch):
    monkeypatch.setenv("DIR_DATOS", str(tmp_path))
    olvidar_backend()
    ajustes = importlib.import_module("backend.ajustes")
    assert ajustes.DIR_DATOS == tmp_path, "el test escribiría en la carpeta de datos real"
    mod = importlib.import_module("backend.clasificacion")
    mod.preparar()
    yield mod
    olvidar_backend()


def test_la_escala_tiene_cinco_opciones_ordenadas(clasificacion):
    valores = [o["valor"] for o in clasificacion.ESCALA]
    assert valores == [-2, -1, 0, 1, 2]
    assert len(clasificacion.CODIGOS) == 5


def test_guardar_y_leer_lo_propio(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si", "se ve una rampa")
    mia = clasificacion.mia("nodoA", 7, "ana")
    assert mia["respuesta"] == "si"
    assert mia["comentario"] == "se ve una rampa"


def test_una_respuesta_desconocida_se_rechaza(clasificacion):
    with pytest.raises(ValueError):
        clasificacion.guardar("nodoA", 7, "ana", "quizas")


def test_dos_revisores_no_se_pisan(clasificacion):
    """El requisito central: la clasificación es por persona, no global."""
    clasificacion.guardar("nodoA", 7, "ana", "si_definitivo")
    clasificacion.guardar("nodoA", 7, "beto", "no")
    assert clasificacion.mia("nodoA", 7, "ana")["respuesta"] == "si_definitivo"
    assert clasificacion.mia("nodoA", 7, "beto")["respuesta"] == "no"
    assert len(clasificacion.de_evento("nodoA", 7)) == 2


def test_corregir_pisa_la_respuesta_pero_conserva_cuando_se_miro(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "neutral", "primera impresión")
    primera = clasificacion.mia("nodoA", 7, "ana")
    clasificacion.guardar("nodoA", 7, "ana", "si", "lo miré de nuevo")
    segunda = clasificacion.mia("nodoA", 7, "ana")
    assert segunda["respuesta"] == "si"
    assert segunda["comentario"] == "lo miré de nuevo"
    assert segunda["creado_en"] == primera["creado_en"]


def test_la_misma_persona_en_otra_rama_arranca_de_cero(clasificacion):
    """Decisión firmada: la clasificación pertenece a la corrida donde se hizo (nodo + event_id)."""
    clasificacion.guardar("nodoA", 7, "ana", "si")
    assert clasificacion.mia("nodoB", 7, "ana") is None


def test_del_nodo_devuelve_solo_lo_mio(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "ana", "no")
    clasificacion.guardar("nodoA", 3, "beto", "no")
    mias = clasificacion.del_nodo("nodoA", "ana")
    assert sorted(mias) == [1, 2]


def test_el_comentario_se_recorta_y_no_hace_falta(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si", "x" * 9000)
    assert len(clasificacion.mia("nodoA", 1, "ana")["comentario"]) == clasificacion.MAX_COMENTARIO
    clasificacion.guardar("nodoA", 2, "ana", "si")
    assert clasificacion.mia("nodoA", 2, "ana")["comentario"] == ""


def test_cuantas_en_cuenta_el_trabajo_en_riesgo(clasificacion):
    """Lo usa el borrado en cascada para poder avisar antes de llevarse trabajo humano."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "beto", "no")
    clasificacion.guardar("nodoB", 1, "ana", "si")
    assert clasificacion.cuantas_en(["nodoA"]) == 2
    assert clasificacion.cuantas_en(["nodoA", "nodoB"]) == 3
    assert clasificacion.cuantas_en([]) == 0


def test_resumen_del_nodo(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "ana", "si")
    clasificacion.guardar("nodoA", 1, "beto", "no")
    r = clasificacion.resumen_nodo("nodoA")
    assert r["total"] == 3
    assert r["revisores"] == 2
    assert r["reparto"] == {"si": 2, "no": 1}


# --- retirar el voto ---------------------------------------------------------------------------
#
# El retiro es la única operación del módulo que borra. Lo que hay que fijar acá es que borre SOLO
# lo que corresponde: el evento del que se habla, y de la persona que lo pide. Un retiro que se
# lleve puesto el juicio de otro revisor rompería el requisito central del módulo, y sería
# invisible hasta que alguien comparara coincidencias entre revisores.


def test_retirar_deja_el_evento_sin_clasificar(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si", "una rampa")
    assert clasificacion.retirar("nodoA", 7, "ana") is True
    assert clasificacion.mia("nodoA", 7, "ana") is None


def test_retirar_lo_que_no_existe_avisa_en_vez_de_fingir(clasificacion):
    """`False` es lo que le permite a la API responder 404 en lugar de un éxito vacío."""
    assert clasificacion.retirar("nodoA", 7, "ana") is False


def test_retirar_no_toca_el_juicio_de_otro_revisor(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si_definitivo")
    clasificacion.guardar("nodoA", 7, "beto", "no")
    clasificacion.retirar("nodoA", 7, "ana")
    assert clasificacion.mia("nodoA", 7, "ana") is None
    assert clasificacion.mia("nodoA", 7, "beto")["respuesta"] == "no"
    assert len(clasificacion.de_evento("nodoA", 7)) == 1


def test_retirar_no_toca_los_demas_eventos_ni_las_demas_ramas(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si")
    clasificacion.guardar("nodoA", 8, "ana", "no")
    clasificacion.guardar("nodoB", 7, "ana", "neutral")
    clasificacion.retirar("nodoA", 7, "ana")
    assert clasificacion.mia("nodoA", 8, "ana")["respuesta"] == "no"
    assert clasificacion.mia("nodoB", 7, "ana")["respuesta"] == "neutral"


def test_retirar_sale_de_las_cuentas(clasificacion):
    """Un evento retirado no debe seguir contando como respondido en ninguna de las dos métricas."""
    clasificacion.guardar("nodoA", 7, "ana", "si")
    clasificacion.guardar("nodoA", 8, "ana", "si")
    assert clasificacion.cuantas_en(["nodoA"]) == 2
    assert clasificacion.resumen_nodo("nodoA")["reparto"] == {"si": 2}

    clasificacion.retirar("nodoA", 7, "ana")
    assert clasificacion.cuantas_en(["nodoA"]) == 1
    r = clasificacion.resumen_nodo("nodoA")
    assert r["total"] == 1
    assert r["reparto"] == {"si": 1}


def test_volver_a_votar_despues_de_retirar_arranca_de_cero(clasificacion):
    """No queda media fila escondida: el alta posterior es un alta, no una corrección.

    `creado_en` tiene que ser el del voto nuevo. Si el retiro hubiera dejado la fila marcada en vez
    de borrarla, el `ON CONFLICT` de `guardar` la habría reutilizado y este evento arrastraría la
    fecha de un juicio que su autor retiró.
    """
    clasificacion.guardar("nodoA", 7, "ana", "no", "me parece que no")
    vieja = clasificacion.mia("nodoA", 7, "ana")
    clasificacion.retirar("nodoA", 7, "ana")
    clasificacion.guardar("nodoA", 7, "ana", "si")
    nueva = clasificacion.mia("nodoA", 7, "ana")
    assert nueva["respuesta"] == "si"
    assert nueva["comentario"] == ""
    assert nueva["creado_en"] >= vieja["creado_en"]


# --- se va con la rama ------------------------------------------------------------------------


def test_borrar_de_se_lleva_las_de_esas_ramas_y_solo_esas(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "beto", "no")
    clasificacion.guardar("nodoB", 1, "ana", "neutral")
    assert clasificacion.borrar_de(["nodoA"]) == 2
    assert clasificacion.mia("nodoA", 1, "ana") is None
    assert clasificacion.mia("nodoB", 1, "ana")["respuesta"] == "neutral"


def test_borrar_de_se_lleva_la_de_todos_los_revisores(clasificacion):
    """No es «lo mío en esa rama»: la rama se va, y con ella el juicio de cualquiera."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 1, "beto", "no")
    clasificacion.guardar("nodoA", 1, "caro", "neutral")
    assert clasificacion.borrar_de(["nodoA"]) == 3
    assert clasificacion.de_evento("nodoA", 1) == []


def test_borrar_de_acepta_la_cascada_entera(clasificacion):
    """`delete_nodo` pasa el nodo y sus descendientes de una vez."""
    for n in ("raiz", "hijo", "nieto"):
        clasificacion.guardar(n, 1, "ana", "si")
    clasificacion.guardar("otra-rama", 1, "ana", "si")
    assert clasificacion.borrar_de(["raiz", "hijo", "nieto"]) == 3
    assert clasificacion.cuantas_en(["raiz", "hijo", "nieto"]) == 0
    assert clasificacion.cuantas_en(["otra-rama"]) == 1


def test_borrar_de_sin_ramas_no_toca_nada(clasificacion):
    """Una lista vacía no puede convertirse en un `DELETE` sin `WHERE`."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    assert clasificacion.borrar_de([]) == 0
    assert clasificacion.mia("nodoA", 1, "ana")["respuesta"] == "si"


def test_cuantas_en_es_lo_que_borrar_de_se_llevaria(clasificacion):
    """Las dos mitades del aviso: `cuantas_en` dice el número que el 409 muestra, `borrar_de` lo
    ejecuta. Si dejaran de coincidir, el aviso mentiría."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "beto", "no")
    clasificacion.guardar("nodoB", 9, "ana", "si")
    anunciadas = clasificacion.cuantas_en(["nodoA", "nodoB"])
    assert clasificacion.borrar_de(["nodoA", "nodoB"]) == anunciadas


# --- la migración de las seis columnas muertas ------------------------------------------------


def test_la_migracion_quita_las_columnas_viejas_y_conserva_las_filas(clasificacion, tmp_path):
    """Una base con el esquema anterior tiene que quedar limpia SIN perder los juicios.

    Se arma a mano el esquema viejo, con una fila que trae la copia del evento, y se abre con el
    módulo actual. Es el camino que van a recorrer las bases que ya existen —10 filas en la máquina
    de desarrollo, 3 en el servidor— y sin este test la migración se probaría por primera vez ahí.
    """
    import sqlite3

    base = tmp_path / "revision" / "clasificacion.sqlite"
    base.parent.mkdir(parents=True, exist_ok=True)
    clasificacion.conexion().close()
    clasificacion._con = None
    base.unlink(missing_ok=True)

    vieja = sqlite3.connect(base)
    vieja.executescript("""
        CREATE TABLE clasificaciones (
            nodo TEXT NOT NULL, event_id INTEGER NOT NULL, usuario TEXT NOT NULL,
            respuesta TEXT NOT NULL, comentario TEXT NOT NULL DEFAULT '',
            creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL,
            hoja TEXT, segmento TEXT, desde INTEGER, hasta INTEGER,
            n_ventanas INTEGER, n_detectores INTEGER,
            PRIMARY KEY (nodo, event_id, usuario));
    """)
    vieja.execute(
        "INSERT INTO clasificaciones VALUES ('nodoV', 3, 'ana', 'si', 'juicio viejo',"
        " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00',"
        " 'August 26', 'August 26#0', 100, 165, 15, 5)")
    vieja.commit()
    vieja.close()

    con = clasificacion.preparar()
    columnas = [f["name"] for f in con.execute("PRAGMA table_info(clasificaciones)")]
    assert columnas == ["nodo", "event_id", "usuario", "respuesta", "comentario",
                        "creado_en", "actualizado_en"]

    mia = clasificacion.mia("nodoV", 3, "ana")
    assert mia["respuesta"] == "si"
    assert mia["comentario"] == "juicio viejo"
    assert mia["creado_en"] == "2026-01-01T00:00:00+00:00"


def test_la_migracion_no_se_queja_en_una_base_ya_migrada(clasificacion):
    """Corre en cada arranque, así que tiene que ser idempotente."""
    con = clasificacion.conexion()
    assert clasificacion._migrar(con) == []
    assert clasificacion._migrar(con) == []


# --- el catálogo de la Etapa 2.5 --------------------------------------------------------------


def test_catalogado_agrupa_por_rama_y_evento(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 1, "beto", "no")
    clasificacion.guardar("nodoA", 2, "ana", "neutral")
    clasificacion.guardar("nodoB", 5, "beto", "si_definitivo")
    cat = clasificacion.catalogado()
    assert set(cat) == {"nodoA", "nodoB"}
    assert set(cat["nodoA"]) == {1, 2}
    assert [r["usuario"] for r in cat["nodoA"][1]] == ["ana", "beto"]
    assert cat["nodoB"][5][0]["respuesta"] == "si_definitivo"


def test_catalogado_trae_los_nombres(clasificacion):
    """A diferencia de todo lo demás del módulo. Su único consumidor es un endpoint de admin: el
    catálogo es la Etapa 2.5, y quien lo mira no es ninguno de los revisores cuya independencia
    hay que preservar."""
    clasificacion.guardar("nodoA", 1, "ana", "si", "se ve una rampa")
    (fila,) = clasificacion.catalogado()["nodoA"][1]
    assert fila["usuario"] == "ana"
    assert fila["comentario"] == "se ve una rampa"


def test_catalogado_vacio_es_un_dict_vacio(clasificacion):
    assert clasificacion.catalogado() == {}


def test_revisores_son_los_que_clasificaron_algo(clasificacion):
    clasificacion.guardar("nodoA", 1, "beto", "si")
    clasificacion.guardar("nodoA", 2, "ana", "no")
    clasificacion.guardar("nodoB", 1, "ana", "si")
    assert clasificacion.revisores() == ["ana", "beto"]


def test_retirar_saca_al_revisor_del_catalogo(clasificacion):
    """Si alguien retira su único juicio, deja de figurar: el catálogo no inventa participantes."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 1, "beto", "no")
    clasificacion.retirar("nodoA", 1, "beto")
    assert clasificacion.revisores() == ["ana"]
    assert [r["usuario"] for r in clasificacion.catalogado()["nodoA"][1]] == ["ana"]


# --- notas sin decisión -----------------------------------------------------------------------
#
# Un comentario sobre un evento que todavía no se juzgó. Existe porque el texto que alguien escribe
# es trabajo, y antes se perdía: la API pedía respuesta y comentario juntos, así que una nota vivía
# en un borrador del navegador hasta la primera recarga.


def test_una_nota_sin_decision_se_guarda(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", None, "esto conviene verlo con Elias")
    mia = clasificacion.mia("nodoA", 1, "ana")
    assert mia["respuesta"] is None
    assert mia["comentario"] == "esto conviene verlo con Elias"


def test_una_fila_sin_decision_y_sin_texto_se_rechaza(clasificacion):
    """No sería el registro de nada. Pasa cada vez que se abre un evento y no se toca."""
    with pytest.raises(ValueError):
        clasificacion.guardar("nodoA", 1, "ana", None, "")
    with pytest.raises(ValueError):
        clasificacion.guardar("nodoA", 1, "ana", None, "   ")
    assert clasificacion.mia("nodoA", 1, "ana") is None


def test_una_nota_se_puede_convertir_en_decision_conservando_cuando_se_miro(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", None, "no sé todavía")
    nota = clasificacion.mia("nodoA", 1, "ana")
    clasificacion.guardar("nodoA", 1, "ana", "si", "ahora sí: es una rampa")
    ya = clasificacion.mia("nodoA", 1, "ana")
    assert ya["respuesta"] == "si"
    assert ya["creado_en"] == nota["creado_en"], "la nota fue el primer contacto con el evento"


def test_una_decision_puede_volver_a_ser_nota(clasificacion):
    """Es lo que pasa al retirar un juicio dejando el comentario escrito."""
    clasificacion.guardar("nodoA", 1, "ana", "si", "me parece anómalo")
    clasificacion.guardar("nodoA", 1, "ana", None, "me parece anómalo")
    assert clasificacion.mia("nodoA", 1, "ana")["respuesta"] is None


def test_una_nota_no_cuenta_como_decision_en_el_resumen(clasificacion):
    """La separación importa: mezclarlas haría indistinguible «no se pronunció» de «dijo neutral»,
    que es exactamente lo que la Etapa 2 necesita poder separar."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "ana", None, "una nota")
    clasificacion.guardar("nodoA", 3, "beto", "no")
    r = clasificacion.resumen_nodo("nodoA")
    assert r["total"] == 2, "las decisiones"
    assert r["reparto"] == {"si": 1, "no": 1}
    assert r["notas"] == 1
    assert r["revisores"] == 2, "quien dejó una nota participó"


def test_una_nota_si_cuenta_en_lo_que_el_borrado_se_llevaria(clasificacion):
    """`cuantas_en` mide «cuánto se pierde», no «cuánto se juzgó»: una nota es texto que se va."""
    clasificacion.guardar("nodoA", 1, "ana", "si")
    clasificacion.guardar("nodoA", 2, "ana", None, "una nota")
    assert clasificacion.cuantas_en(["nodoA"]) == 2
    assert clasificacion.resumen_nodo("nodoA")["total"] == 1


def test_una_nota_aparece_en_el_catalogo(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", None, "revisar con el experto")
    (fila,) = clasificacion.catalogado()["nodoA"][1]
    assert fila["respuesta"] is None
    assert fila["comentario"] == "revisar con el experto"
    assert clasificacion.revisores() == ["ana"]


def test_retirar_se_lleva_tambien_la_nota(clasificacion):
    """Retirar es quitar la fila entera. Dejar el comentario huérfano de decisión es otra cosa —se
    hace guardando con `respuesta=None`— y la hace el frontend cuando queda texto escrito."""
    clasificacion.guardar("nodoA", 1, "ana", None, "una nota")
    assert clasificacion.retirar("nodoA", 1, "ana") is True
    assert clasificacion.mia("nodoA", 1, "ana") is None


def test_la_migracion_deja_respuesta_admitir_nulos(clasificacion, tmp_path):
    """Una base creada cuando `respuesta` era obligatoria tiene que poder recibir notas.

    SQLite no sabe quitar un `NOT NULL` con `ALTER TABLE`, así que la migración recrea la tabla y
    copia las filas; lo que hay que verificar es que no se pierda ninguna en el camino.
    """
    import sqlite3

    base = tmp_path / "revision" / "clasificacion.sqlite"
    base.parent.mkdir(parents=True, exist_ok=True)
    clasificacion.conexion().close()
    clasificacion._con = None
    base.unlink(missing_ok=True)

    vieja = sqlite3.connect(base)
    vieja.executescript("""
        CREATE TABLE clasificaciones (
            nodo TEXT NOT NULL, event_id INTEGER NOT NULL, usuario TEXT NOT NULL,
            respuesta TEXT NOT NULL, comentario TEXT NOT NULL DEFAULT '',
            creado_en TEXT NOT NULL, actualizado_en TEXT NOT NULL,
            PRIMARY KEY (nodo, event_id, usuario));
    """)
    vieja.execute("INSERT INTO clasificaciones VALUES ('nodoV', 3, 'ana', 'si', 'ya estaba',"
                  " '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')")
    vieja.commit()
    vieja.close()

    con = clasificacion.preparar()
    col = next(f for f in con.execute("PRAGMA table_info(clasificaciones)")
               if f["name"] == "respuesta")
    assert not col["notnull"], "sigue siendo obligatoria"

    vieja_fila = clasificacion.mia("nodoV", 3, "ana")
    assert vieja_fila["respuesta"] == "si"
    assert vieja_fila["comentario"] == "ya estaba"
    assert vieja_fila["creado_en"] == "2026-01-01T00:00:00+00:00"

    clasificacion.guardar("nodoV", 4, "ana", None, "y ahora una nota")
    assert clasificacion.mia("nodoV", 4, "ana")["respuesta"] is None

    indices = {f["name"] for f in con.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='clasificaciones'")}
    assert {"idx_clas_nodo", "idx_clas_usuario"} <= indices, "los índices se van con la tabla vieja"


def test_la_migracion_de_nulos_no_se_queja_en_una_base_al_dia(clasificacion):
    con = clasificacion.conexion()
    assert clasificacion._migrar_respuesta_opcional(con) is False
    assert clasificacion._migrar_respuesta_opcional(con) is False


# --- secciones de un evento ------------------------------------------------------------------
#
# Un evento largo puede tener varias secciones, cada una con su propia respuesta. Lo que importa
# afirmar: que caen dentro del evento, que no se enciman, que son de quien las marcó y que se van
# con la rama igual que las respuestas.

LIM = (100, 200)    # el (start, end) del evento


def test_una_seccion_se_guarda_sin_respuesta_y_despues_se_completa(clasificacion):
    s = clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM)
    assert (s["desde"], s["hasta"], s["respuesta"]) == (120, 140, None)
    e = clasificacion.editar_seccion(s["id"], "nodoA", 7, "ana", 120, 145, LIM, "si", "caída")
    assert (e["hasta"], e["respuesta"], e["comentario"]) == (145, "si", "caída")
    assert e["creado_en"] == s["creado_en"]


def test_varias_secciones_por_evento_en_orden_de_medicion(clasificacion):
    clasificacion.agregar_seccion("nodoA", 7, "ana", 170, 190, LIM, "neutral")
    clasificacion.agregar_seccion("nodoA", 7, "ana", 100, 110, LIM, "si_definitivo")
    secs = clasificacion.secciones_del_nodo("nodoA", "ana")[7]
    assert [(s["desde"], s["respuesta"]) for s in secs] == [(100, "si_definitivo"), (170, "neutral")]


@pytest.mark.parametrize("desde,hasta", [(90, 120), (190, 201), (150, 150), (160, 150)])
def test_una_seccion_fuera_del_evento_o_vacia_se_rechaza(clasificacion, desde, hasta):
    with pytest.raises(ValueError):
        clasificacion.agregar_seccion("nodoA", 7, "ana", desde, hasta, LIM)


def test_los_bordes_del_evento_se_admiten(clasificacion):
    clasificacion.agregar_seccion("nodoA", 7, "ana", 100, 200, LIM)


def test_dos_secciones_propias_no_se_enciman_pero_pueden_tocarse(clasificacion):
    clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM)
    with pytest.raises(ValueError):
        clasificacion.agregar_seccion("nodoA", 7, "ana", 139, 150, LIM)
    clasificacion.agregar_seccion("nodoA", 7, "ana", 140, 150, LIM)


def test_editar_una_seccion_no_choca_consigo_misma_pero_si_con_las_otras(clasificacion):
    a = clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM)
    clasificacion.agregar_seccion("nodoA", 7, "ana", 150, 160, LIM)
    clasificacion.editar_seccion(a["id"], "nodoA", 7, "ana", 115, 145, LIM)
    with pytest.raises(ValueError):
        clasificacion.editar_seccion(a["id"], "nodoA", 7, "ana", 115, 155, LIM)


def test_las_secciones_de_otro_revisor_no_cuentan_como_encimadas(clasificacion):
    """El ciego vale también acá: lo que marcó otro no le restringe nada a nadie."""
    clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM)
    clasificacion.agregar_seccion("nodoA", 7, "beto", 120, 140, LIM)
    assert 7 not in clasificacion.secciones_del_nodo("nodoA", "carla")


def test_nadie_edita_ni_quita_la_seccion_de_otro(clasificacion):
    s = clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM, "si")
    assert clasificacion.editar_seccion(s["id"], "nodoA", 7, "beto", 120, 140, LIM, "no") is None
    assert clasificacion.quitar_seccion(s["id"], "nodoA", 7, "beto") is False
    assert clasificacion.secciones_del_nodo("nodoA", "ana")[7][0]["respuesta"] == "si"


def test_quitar_una_seccion(clasificacion):
    s = clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM)
    assert clasificacion.quitar_seccion(s["id"], "nodoA", 7, "ana") is True
    assert clasificacion.quitar_seccion(s["id"], "nodoA", 7, "ana") is False
    assert clasificacion.secciones_del_nodo("nodoA", "ana") == {}


def test_una_seccion_con_respuesta_desconocida_se_rechaza(clasificacion):
    with pytest.raises(ValueError):
        clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM, "quizas")


def test_hay_un_tope_de_secciones_por_evento(clasificacion):
    for k in range(clasificacion.MAX_SECCIONES):
        clasificacion.agregar_seccion("nodoA", 7, "ana", 100 + k * 2, 101 + k * 2, LIM)
    with pytest.raises(ValueError):
        clasificacion.agregar_seccion("nodoA", 7, "ana", 190, 195, LIM)


def test_retirar_la_respuesta_del_evento_no_toca_sus_secciones(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si")
    clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM, "si")
    clasificacion.retirar("nodoA", 7, "ana")
    assert len(clasificacion.secciones_del_nodo("nodoA", "ana")[7]) == 1


def test_las_secciones_se_van_con_su_rama_y_cuentan_en_el_aviso(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si")
    clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM)
    clasificacion.agregar_seccion("nodoB", 7, "ana", 120, 140, LIM)
    assert clasificacion.cuantas_en(["nodoA"]) == 2
    assert clasificacion.borrar_de(["nodoA"]) == 2
    assert clasificacion.secciones_del_nodo("nodoA", "ana") == {}
    assert 7 in clasificacion.secciones_del_nodo("nodoB", "ana")


def test_el_catalogo_trae_las_secciones_de_cada_respuesta(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si")
    clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM, "si_definitivo")
    (fila,) = clasificacion.catalogado()["nodoA"][7]
    assert [(s["desde"], s["hasta"], s["respuesta"]) for s in fila["secciones"]] == [
        (120, 140, "si_definitivo")]


def test_secciones_sin_respuesta_de_conjunto_aparecen_en_el_catalogo(clasificacion):
    clasificacion.guardar("nodoA", 7, "beto", "no")
    clasificacion.agregar_seccion("nodoA", 7, "ana", 120, 140, LIM, "si")
    filas = clasificacion.catalogado()["nodoA"][7]
    assert [(r["usuario"], r["respuesta"]) for r in filas] == [("ana", None), ("beto", "no")]
    assert len(filas[0]["secciones"]) == 1
    assert clasificacion.revisores() == ["ana", "beto"]

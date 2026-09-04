"""La encuesta de eventos: que sea por persona, que se pueda corregir y que no se pierda.

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


EVENTO = {"SheetName": "August 26", "segment": "August 26#0", "start": 100, "end": 165,
          "n_ventanas": 15, "n_detectores": 5}


def test_la_escala_tiene_cinco_opciones_ordenadas(clasificacion):
    valores = [o["valor"] for o in clasificacion.ESCALA]
    assert valores == [-2, -1, 0, 1, 2]
    assert len(clasificacion.CODIGOS) == 5


def test_guardar_y_leer_lo_propio(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "si", "se ve una rampa", evento=EVENTO)
    mia = clasificacion.mia("nodoA", 7, "ana")
    assert mia["respuesta"] == "si"
    assert mia["comentario"] == "se ve una rampa"


def test_una_respuesta_desconocida_se_rechaza(clasificacion):
    with pytest.raises(ValueError):
        clasificacion.guardar("nodoA", 7, "ana", "quizas")


def test_dos_revisores_no_se_pisan(clasificacion):
    """El requisito central: la clasificación es por persona, no global."""
    clasificacion.guardar("nodoA", 7, "ana", "si_definitivo", evento=EVENTO)
    clasificacion.guardar("nodoA", 7, "beto", "no", evento=EVENTO)
    assert clasificacion.mia("nodoA", 7, "ana")["respuesta"] == "si_definitivo"
    assert clasificacion.mia("nodoA", 7, "beto")["respuesta"] == "no"
    assert len(clasificacion.de_evento("nodoA", 7)) == 2


def test_corregir_pisa_la_respuesta_pero_conserva_cuando_se_miro(clasificacion):
    clasificacion.guardar("nodoA", 7, "ana", "neutral", "primera impresión", evento=EVENTO)
    primera = clasificacion.mia("nodoA", 7, "ana")
    clasificacion.guardar("nodoA", 7, "ana", "si", "lo miré de nuevo", evento=EVENTO)
    segunda = clasificacion.mia("nodoA", 7, "ana")
    assert segunda["respuesta"] == "si"
    assert segunda["comentario"] == "lo miré de nuevo"
    assert segunda["creado_en"] == primera["creado_en"]


def test_la_correccion_no_reescribe_la_copia_del_evento(clasificacion):
    """Solo el alta escribe el contexto: una corrección con datos de otra corrida no puede
    cambiar el rango con el que se emitió el juicio."""
    clasificacion.guardar("nodoA", 7, "ana", "si", evento=EVENTO)
    clasificacion.guardar("nodoA", 7, "ana", "no", evento={**EVENTO, "SheetName": "OTRA HOJA"})
    assert clasificacion.mia("nodoA", 7, "ana")["hoja"] == "August 26"


def test_la_copia_del_evento_sobrevive_al_borrado_de_la_rama(clasificacion):
    """Por esto se denormaliza: si la rama se borra, la respuesta tiene que seguir siendo legible."""
    clasificacion.guardar("nodoA", 7, "ana", "si", evento=EVENTO)
    fila = clasificacion.mia("nodoA", 7, "ana")
    assert (fila["hoja"], fila["desde"], fila["hasta"]) == ("August 26", 100, 165)
    assert fila["n_detectores"] == 5


def test_la_misma_persona_en_otra_rama_arranca_de_cero(clasificacion):
    """Decisión firmada: la clasificación pertenece a la corrida donde se hizo (nodo + event_id)."""
    clasificacion.guardar("nodoA", 7, "ana", "si", evento=EVENTO)
    assert clasificacion.mia("nodoB", 7, "ana") is None


def test_del_nodo_devuelve_solo_lo_mio(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si", evento=EVENTO)
    clasificacion.guardar("nodoA", 2, "ana", "no", evento=EVENTO)
    clasificacion.guardar("nodoA", 3, "beto", "no", evento=EVENTO)
    mias = clasificacion.del_nodo("nodoA", "ana")
    assert sorted(mias) == [1, 2]


def test_el_comentario_se_recorta_y_no_hace_falta(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si", "x" * 9000, evento=EVENTO)
    assert len(clasificacion.mia("nodoA", 1, "ana")["comentario"]) == clasificacion.MAX_COMENTARIO
    clasificacion.guardar("nodoA", 2, "ana", "si", evento=EVENTO)
    assert clasificacion.mia("nodoA", 2, "ana")["comentario"] == ""


def test_cuantas_en_cuenta_el_trabajo_en_riesgo(clasificacion):
    """Lo usa el borrado en cascada para poder avisar antes de llevarse trabajo humano."""
    clasificacion.guardar("nodoA", 1, "ana", "si", evento=EVENTO)
    clasificacion.guardar("nodoA", 2, "beto", "no", evento=EVENTO)
    clasificacion.guardar("nodoB", 1, "ana", "si", evento=EVENTO)
    assert clasificacion.cuantas_en(["nodoA"]) == 2
    assert clasificacion.cuantas_en(["nodoA", "nodoB"]) == 3
    assert clasificacion.cuantas_en([]) == 0


def test_resumen_del_nodo(clasificacion):
    clasificacion.guardar("nodoA", 1, "ana", "si", evento=EVENTO)
    clasificacion.guardar("nodoA", 2, "ana", "si", evento=EVENTO)
    clasificacion.guardar("nodoA", 1, "beto", "no", evento=EVENTO)
    r = clasificacion.resumen_nodo("nodoA")
    assert r["total"] == 3
    assert r["revisores"] == 2
    assert r["reparto"] == {"si": 2, "no": 1}

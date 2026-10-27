"""El archivo que lee la Etapa 2 de la tesis: que lleve el rango de cada evento y nada se pierda.

Del otro lado (`tesis.etiquetas.cargar_juicios`) el formato está fijado por número de versión, así
que un campo que cambie de nombre acá rompe allá. Estos tests son el contrato visto desde este lado.
"""

import importlib.util
from pathlib import Path

import pandas as pd
import pytest

RAIZ = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def exportar():
    spec = importlib.util.spec_from_file_location("exportar_juicios",
                                                  RAIZ / "scripts" / "exportar_juicios.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CADENA = [
    {"etapa": "datos", "parametros": {}},
    {"etapa": "ventaneo", "parametros": {"tamano_ventana": 50, "deduplicar": True}},
    {"etapa": "eventos", "parametros": {"fraccion_candidatos": 0.01, "max_ventanas_evento": 15}},
]
NODO = {"clave": "abc123", "etiqueta": "tesis", "commit_tesis": "0baac87"}
TABLA = pd.DataFrame({"event_id": [6, 1], "SheetName": ["August 26", "April 20"],
                      "segment": [3, 7], "start": [237, 547], "end": [337, 600]})


def test_la_config_sale_con_los_nombres_de_la_tesis(exportar):
    assert exportar.config_de_la_rama(CADENA) == {
        "window_size": 50, "use_dedup": True, "candidate_fraction": 0.01, "max_event_windows": 15}


def test_sin_tope_de_ventanas_es_none(exportar):
    cadena = [dict(n) for n in CADENA]
    cadena[2] = {"etapa": "eventos", "parametros": {"fraccion_candidatos": 0.05,
                                                    "max_ventanas_evento": 0}}
    assert exportar.config_de_la_rama(cadena)["max_event_windows"] is None


def test_armar_lleva_rango_revisores_y_secciones(exportar):
    juicios = {6: [
        {"usuario": "ana", "respuesta": None, "comentario": "",
         "secciones": [{"id": 3, "desde": 264, "hasta": 300, "respuesta": "si",
                        "comentario": "caída", "actualizado_en": "x"}]},
        {"usuario": "beto", "respuesta": "no", "comentario": "ruido", "secciones": []},
    ]}
    a = exportar.armar(NODO, CADENA, TABLA, juicios, {"ana": 3})
    assert a["formato"] == "juicios-taller/1" and a["nodo"] == "abc123"
    assert a["commit_tesis"] == "0baac87"
    (ev,) = a["eventos"]
    assert (ev["event_id"], ev["hoja"], ev["segmento"], ev["desde"], ev["hasta"]) == (
        6, "August 26", 3, 237, 337)
    ana, beto = ev["revisores"]
    assert ana["secciones"] == [{"desde": 264, "hasta": 300, "respuesta": "si",
                                 "comentario": "caída"}]
    assert (beto["respuesta"], beto["comentario"]) == ("no", "ruido")
    # El grado de cada revisor; quien no tiene cuenta (o no lo tiene cargado) sale con `None`.
    assert (ana["experiencia"], beto["experiencia"]) == (3, None)


def test_solo_van_los_eventos_que_alguien_toco(exportar):
    a = exportar.armar(NODO, CADENA, TABLA, {})
    assert a["eventos"] == []


def test_un_juicio_sobre_un_evento_que_no_esta_se_avisa(exportar):
    with pytest.raises(ValueError):
        exportar.armar(NODO, CADENA, TABLA, {99: [{"usuario": "ana", "respuesta": "si",
                                                   "comentario": "", "secciones": []}]})


def test_el_archivo_es_json_valido_con_tipos_de_numpy(exportar):
    import json
    a = exportar.armar(NODO, CADENA, TABLA, {1: [{"usuario": "ana", "respuesta": "si",
                                                  "comentario": "", "secciones": []}]})
    json.dumps(a)   # `segment` llega como int64 desde pandas

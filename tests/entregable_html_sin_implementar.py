"""INACTIVO — este test no corre, y el nombre del archivo es lo que lo mantiene así.

    Pytest recoge `test_*.py`. Este archivo NO se llama así a propósito: prueba una función
    (`main.get_entregable`) que hoy no existe, y mientras estuvo en la suite la dejaba en rojo.
    Un test que siempre falla enseña a ignorar los fallos, que es peor que no tenerlo.

QUÉ PASÓ. Se escribió junto con una vista que mostraba los tres entregables como HTML en la
página, sin descargar el `.xlsx`. Esa vista se perdió: quedó sin commitear entre el 24 de agosto
y el 1 de septiembre, y un `git reset --hard` previo a un `git pull` se la llevó. Este archivo
sobrevivió solo porque estaba sin rastrear, y un reset no toca lo que git no conoce.

POR QUÉ NO SE REHIZO. La revisión experta (`revision.py`, ADR A16) resolvió la misma necesidad
por otro camino: abre el entregable en un editor dentro del navegador. Y lo hace sobre el
archivo generado, no sobre una segunda representación del mismo dato — así que el riesgo que
este test cuidaba, que la página y el Excel se separen, dejó de existir por construcción.

SI ALGÚN DÍA VUELVE. Hace falta reponer `main.get_entregable` y `main._nodo_de_eventos`, y
renombrar este archivo a `test_entregable.py`. Lo de abajo sigue siendo el pliego de lo que la
vista tenía que cumplir.

────────────────────────────────────────────────────────────────────────────────────────────

La tabla que se ve en la página y la que se descarga en Excel son la misma.

POR QUÉ EXISTE. El taller ahora muestra los candidatos consolidados en pantalla además de
ofrecerlos como `.xlsx`. Son dos caminos hacia el mismo dato, y ese es exactamente el modo de
falla que el ADR A1 quiere evitar: alguien agrega una columna, ajusta un redondeo o cambia un
orden en uno de los dos, y a partir de ahí la página muestra una cosa y el archivo dice otra
—las dos pareciendo correctas—. Nadie se entera hasta que un resultado defendido no coincide
con el Excel que lo respalda.

La defensa de diseño es que haya UN SOLO productor: `export.build_candidate_table` arma la
tabla, `build_expert_excel` la escribe y el endpoint la serializa. Este test comprueba que esa
promesa se cumple de verdad, comparando el archivo generado contra el JSON del endpoint celda
por celda. Si alguien calcula algo de un lado, la suite se rompe.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("tesis", reason="hace falta el paquete de la tesis instalado (mise run install)")
pytest.importorskip("openpyxl", reason="hace falta openpyxl para leer el Excel generado")

from backend import almacen, main  # noqa: E402


def _clave_de_eventos() -> str | None:
    """Un nodo de eventos ya ejecutado, si el árbol local tiene alguno."""
    try:
        nodos = almacen.listar(main._con)
    except Exception:
        return None
    for n in nodos:
        if n["etapa"] == "eventos" and n["estado"] == "listo" and n["tiene_resultado"]:
            return n["clave"]
    return None


@pytest.fixture(scope="module")
def clave() -> str:
    c = _clave_de_eventos()
    if c is None:
        pytest.skip("el árbol local no tiene un nodo de eventos ejecutado")
    return c


def _mismo_numero(a, b) -> bool:
    """Compara tolerando el viaje por JSON y por la celda del Excel.

    `None` de un lado y `NaN` del otro son el mismo hueco: el endpoint convierte los `NaN` a
    `None` porque JSON no los tiene, y openpyxl los devuelve como `None` o como float NaN según
    cómo se hayan escrito.
    """
    vacio = (lambda v: v is None or (isinstance(v, float) and math.isnan(v)))
    if vacio(a) and vacio(b):
        return True
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)
    return str(a) == str(b)


def test_la_pagina_y_el_excel_dicen_lo_mismo(clave, tmp_path):
    import openpyxl

    from tesis import export

    desde_la_pagina = main.get_entregable(clave)

    nodo, salida, cfg = main._nodo_de_eventos(clave)
    destino = export.build_expert_excel(
        salida["scores"], salida["meta"], tmp_path / "experto.xlsx",
        features=salida["filtradas"], detection_cfg=cfg,
        window_size=salida["tamano_ventana"],
    )
    hoja = openpyxl.load_workbook(destino).worksheets[0]
    filas_excel = list(hoja.values)
    cabecera, cuerpo = filas_excel[0], filas_excel[1:]

    assert list(cabecera) == desde_la_pagina["columnas"], (
        "las columnas del Excel y las de la página dejaron de coincidir"
    )
    assert len(cuerpo) == len(desde_la_pagina["filas"]), (
        f"el Excel trae {len(cuerpo)} filas y la página {len(desde_la_pagina['filas'])}"
    )
    for i, (fx, fp) in enumerate(zip(cuerpo, desde_la_pagina["filas"])):
        for col, (a, b) in enumerate(zip(fx, fp)):
            assert _mismo_numero(a, b), (
                f"fila {i}, columna «{cabecera[col]}»: el Excel dice {a!r} y la página {b!r}"
            )


def test_el_endpoint_no_inventa_columnas(clave):
    """Las columnas salen del paquete, no de una lista escrita en el taller.

    Si alguien agrega un `map` en `main.py` o en el frontend para «arreglar» un nombre, esto lo
    detecta: la tabla del paquete y la respuesta tienen que tener exactamente las mismas claves.
    """
    from tesis import export

    nodo, salida, cfg = main._nodo_de_eventos(clave)
    tabla = export.build_candidate_table(
        salida["scores"], salida["meta"],
        features=salida["filtradas"], detection_cfg=cfg,
        window_size=salida["tamano_ventana"],
    )
    assert [str(c) for c in tabla.columns] == main.get_entregable(clave)["columnas"]


def test_el_json_no_lleva_nan_ni_infinitos(clave):
    """JSON no tiene `NaN` ni `Infinity`, y `json.dumps` los escribe igual sin protestar.

    El resultado es un cuerpo que `JSON.parse` rechaza en el navegador: la pestaña quedaría
    vacía con un error de sintaxis en la consola, que es de las cosas más molestas de rastrear.
    """
    import json

    d = main.get_entregable(clave)
    crudo = json.dumps(d, allow_nan=False)   # levanta ValueError si quedó algún NaN
    assert "NaN" not in crudo and "Infinity" not in crudo

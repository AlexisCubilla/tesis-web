"""La hoja de procedencia del Excel dice la verdad sobre de qué rama salió.

POR QUÉ EXISTE. El taller produce Excel indistinguibles a simple vista de los oficiales de la
tesis, y lo único que los distingue es esa hoja (ADR A7). Si miente, alguien puede terminar
defendiendo un resultado creyendo que salió de la configuración firmada cuando no.

Y ya mintió una vez: comparando los parámetros como texto JSON, `percentil_baja_var=5` no coincidía
con el `5.0` de la referencia, así que **la configuración de la tesis aparecía apartándose de sí
misma** y todos sus Excel salían marcados como rama exploratoria. El valor sale del backend como
float, pasa por el navegador —que tiene un solo tipo numérico— y vuelve entero.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tesis", reason="hace falta el paquete de la tesis instalado (mise run install)")

from backend import ajustes  # noqa: E402
from backend.main import _diferencias_con_la_tesis, _mismo_valor  # noqa: E402


@pytest.mark.parametrize("a, b, iguales", [
    (5, 5.0, True),        # el que rompía: mismo umbral, distinto tipo
    (5, 6, False),
    (0.95, 0.98, False),
    (True, True, True),
    (True, False, False),
    (True, 1, True),       # en un parámetro booleano es el mismo valor
    (True, 2, False),      # pero no cualquier cosa no nula
    (["a", "b"], ["a", "b"], True),
    (("a", "b"), ["a", "b"], True),      # tupla al guardar, lista al leer de JSON
    (["b", "a"], ["a", "b"], False),     # el orden de los detectores importa
    (["a"], ["a", "b"], False),
])
def test_comparar_parametros_sin_tropezar_con_el_tipo(a, b, iguales):
    assert _mismo_valor(a, b) is iguales


def _cadena(**cambios) -> list[dict]:
    """Una rama con la configuración de referencia, opcionalmente alterada en una etapa."""
    cadena = [{"etapa": e, "parametros": dict(p)} for e, p in ajustes.CONFIG_TESIS.items()]
    for etapa, params in cambios.items():
        for nodo in cadena:
            if nodo["etapa"] == etapa:
                nodo["parametros"].update(params)
    return cadena


def test_la_configuracion_de_la_tesis_no_se_aparta_de_si_misma():
    """El caso que fallaba: sin esto, todo Excel oficial salía marcado como exploratorio."""
    assert _diferencias_con_la_tesis(_cadena()) == []


def test_detecta_un_parametro_cambiado():
    dif = _diferencias_con_la_tesis(_cadena(ventaneo={"tamano_ventana": 100}))
    assert [(e, k) for e, k, _v, _r in dif] == [("ventaneo", "tamano_ventana")]


def test_detecta_cambios_en_varias_etapas():
    dif = _diferencias_con_la_tesis(
        _cadena(datos={"limpiar": False}, eventos={"fraccion_candidatos": 0.05})
    )
    assert {(e, k) for e, k, _v, _r in dif} == {("datos", "limpiar"), ("eventos", "fraccion_candidatos")}

"""El gráfico de un evento trae señal de antes y de después, y dice dónde cae el evento.

POR QUÉ EXISTE. Al revisor se le pregunta «¿esto es un comportamiento anómalo?». Dibujarle solo el
tramo marcado es pedirle que reconozca un valor atípico viendo una muestra de tamaño uno: sin la
señal normal a la vista no tiene contra qué compararlo. El endpoint devuelve ahora un recorte con
contexto a los lados, y este archivo fija las tres cosas que el frontend da por ciertas para poder
dibujarlo:

  · que haya contexto de verdad a los dos lados, y no solo el tramo del evento;
  · que `contexto` diga dónde empieza y termina el evento DENTRO de lo devuelto —de ahí sale el
    sombreado, y un desfasaje ahí sombrea la parte tranquila y deja el evento afuera, sin que nada
    falle;
  · que las coordenadas sean las del tramo contiguo, las mismas que usa `meta["start"]`.

El sistema de coordenadas es la parte delicada. `windowing.make_windows` numera cada ventana con su
posición **dentro de su `segment`**, así que el contexto tiene que salir de las filas de ese mismo
segmento en la etapa `datos`. Salir de cualquier otro lado da un recorte que parece correcto y está
corrido, que es la clase de error que nadie ve en un gráfico.
"""

import pytest

pytest.importorskip("tesis")
pytest.importorskip("fastapi")

from backend import almacen, main  # noqa: E402


def _nodo_con_eventos() -> str | None:
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
    c = _nodo_con_eventos()
    if c is None:
        pytest.skip("el árbol local no tiene un nodo de eventos ejecutado")
    return c


@pytest.fixture(scope="module")
def evento(clave):
    return main.get_evento(clave, 0)


def test_trae_contexto_a_los_dos_lados(evento):
    """Lo dibujado es más largo que el evento, y sobra por izquierda y por derecha.

    Un evento pegado al borde del tramo puede quedarse sin contexto de un lado; el evento 0 de una
    corrida real no lo está, así que acá se exigen los dos. Si esto falla con un margen de cero, es
    que alguien cambió el valor por omisión y el revisor volvió a quedarse sin línea de base.
    """
    c = evento["contexto"]
    assert not c.get("sin_contexto"), "se cayó al camino de reserva: no hay serie del segmento"
    largo_evento = c["evento_hasta"] - c["evento_desde"]
    assert len(evento["valores"]) > largo_evento, "se dibujó solo el evento, sin contexto"
    assert c["evento_desde"] > 0, "no hay señal ANTES del evento"
    assert c["hasta"] - c["desde"] > c["evento_hasta"], "no hay señal DESPUÉS del evento"


def test_el_evento_queda_en_el_tercio_central(evento):
    """El margen por omisión es el largo del evento a cada lado, con piso de una ventana.

    Que la proporción sea siempre la misma es lo que permite mirar dos eventos seguidos sin
    recalibrar el ojo: si un evento saliera ocupando el 80 % del ancho y el siguiente el 10 %, el
    segundo parecería más chico por el encuadre y no por los datos.
    """
    c = evento["contexto"]
    total = len(evento["valores"])
    proporcion = (c["evento_hasta"] - c["evento_desde"]) / total
    assert 0.3 <= proporcion <= 0.36, f"el evento ocupa el {proporcion:.0%} de lo dibujado"


def test_las_coordenadas_son_las_del_tramo(clave, evento):
    """`desde` + `evento_desde` tiene que dar el `start` real del evento.

    Es la afirmación que sostiene el eje x y el sombreado. Si el contexto se sacara de las filas de
    la hoja entera en vez de las del segmento, esta cuenta se rompe — y en el gráfico se vería una
    curva plausible, corrida.
    """
    salida = almacen.cargar_resultado(clave)
    fila = salida["eventos"][salida["eventos"]["event_id"] == 0].iloc[0]
    c = evento["contexto"]
    assert c["desde"] + c["evento_desde"] == int(fila["start"])
    assert c["desde"] + c["evento_hasta"] == int(fila["end"])
    assert c["evento_hasta"] <= len(evento["valores"])


def test_el_margen_se_puede_forzar_y_se_recorta_contra_el_tramo(clave):
    """Un margen enorme trae el tramo entero y no se pasa de sus bordes."""
    d = main.get_evento(clave, 0, margen=100_000)
    c = d["contexto"]
    assert c["desde"] == 0
    assert c["hasta"] == c["tramo"]
    assert len(d["valores"]) == c["tramo"]


def test_las_senales_siguen_siendo_las_del_pipeline(clave, evento):
    """Las columnas dibujadas son las del ventaneo, en su orden. Ni una más, ni reordenadas."""
    salida = almacen.cargar_resultado(clave)
    assert evento["senales"] == list(salida["ventanas"].signal_columns)
    for fila in evento["valores"]:
        assert len(fila) == len(evento["senales"])


def test_el_json_no_lleva_nan(clave):
    """`NaN` haría que `JSON.parse` rechace el cuerpo entero y la pantalla quede vacía."""
    import json

    crudo = json.dumps(main.get_evento(clave, 0), allow_nan=False)
    assert "NaN" not in crudo and "Infinity" not in crudo

"""El taller reproduce los números que la tesis reporta.

POR QUÉ EXISTE ESTE TEST. Es la única afirmación del repositorio que lo hace defendible: si el
taller mostrara números distintos a los de la tesis, sería peor que no tener taller (ver ADR A1).
Hasta ahora esa afirmación vivía en una tabla del README y se comprobaba mirándola.

Y la deriva no es un riesgo hipotético: es el modo de falla esperado de esta arquitectura. El
taller **importa** el paquete `tesis` de un repositorio que evoluciona por su cuenta, que es
justamente el diseño (A1) y la razón de que la interfaz muestre con qué commit está corriendo. Un
ajuste allá que mueva cualquiera de estos números no va a dar error: va a dar *otro número*, en
silencio. Esto lo convierte en un fallo ruidoso.

Los valores esperados son los de la tabla «Verificación» del README. Si cambian por una decisión
firmada en la tesis, se actualizan los dos lugares a la vez.

QUÉ NO HACE. No toca el árbol de ejecuciones ni el caché en disco: ejecuta las etapas en memoria,
que es el mismo camino que usa el trabajador (`trabajos._ejecutar_nodo`) sin la parte de
persistencia.
"""

from __future__ import annotations

import pytest

pytest.importorskip("tesis", reason="hace falta el paquete de la tesis instalado (mise run install)")

from backend import ajustes, almacen, etapas  # noqa: E402  (después del importorskip)

pytestmark = pytest.mark.skipif(
    not almacen.TABLA_CRUDA.exists(),
    reason=f"falta la tabla cruda ({almacen.TABLA_CRUDA}); generala con: mise run datos",
)


def _correr(ajustar: dict[str, dict] | None = None) -> dict[str, dict]:
    """Corre la cadena de seis etapas y devuelve el resumen de cada una.

    Los parámetros son los mismos que usa el botón «★ Correr la de la tesis»: los valores por
    defecto de cada etapa —que ya salen de la configuración de referencia— con la configuración de
    la tesis encima.
    """
    import joblib

    entrada = joblib.load(almacen.TABLA_CRUDA)
    resumenes: dict[str, dict] = {}
    for nombre in etapas.CADENA:
        etapa = etapas.REGISTRO[nombre]
        params = {**etapa.defectos(), **ajustes.CONFIG_TESIS.get(nombre, {})}
        if ajustar and nombre in ajustar:
            params.update(ajustar[nombre])
        entrada, resumenes[nombre] = etapa.ejecutar(entrada, params)
    return resumenes


@pytest.fixture(scope="session")
def oficial() -> dict[str, dict]:
    """La cadena con la configuración con la que la tesis reporta sus resultados (~10 s)."""
    return _correr()


@pytest.fixture(scope="session")
def sin_limpieza() -> dict[str, dict]:
    """La misma cadena apagando la limpieza: el camino del hallazgo H1 (~10 s)."""
    return _correr({"datos": {"limpiar": False}})


def test_la_configuracion_de_referencia_sale_de_la_tesis():
    """Si alguien la pisa por `.env`, los números van a diferir con razón.

    Va primero y por separado para que ese caso no se lea como una regresión del pipeline, que es
    lo que parecería si solo fallaran los números de más abajo.
    """
    origen = ajustes.origen_config()
    assert origen["fuente"] == "paquete de la tesis", (
        f"La configuración de referencia no viene de `tesis.config`, sino de: {origen}. "
        "Los números de abajo solo valen contra la configuración de la tesis."
    )
    assert not origen["sobreescritos"], (
        f"Hay variables TESIS_* del .env pisando la configuración: {origen['sobreescritos']}. "
        "Comentalas para verificar contra la tesis."
    )


# Tabla «Verificación» del README. Un cambio acá tiene que ir acompañado allá.
def test_filas_tras_la_limpieza(oficial):
    assert oficial["datos"]["filas_salida"] == 24_138


def test_ventanas_tras_el_dedup(oficial):
    assert oficial["ventaneo"]["ventanas_conservadas"] == 6_102


def test_caracteristicas_finales(oficial):
    assert oficial["filtrado"]["features_salida"] == 45


def test_eventos_candidatos(oficial):
    assert oficial["eventos"]["eventos"] == 40


def test_eventos_en_el_limite_de_quince(oficial):
    """Los que tocan el tope de ventanas por evento firmado en la tesis (ADR-0008)."""
    assert oficial["eventos"]["en_el_limite"] == 3


# El hallazgo H1: apagar la limpieza reproduce el camino del borrador previo. Es la comparación que
# sostiene el hallazgo, así que también tiene que seguir dando lo mismo.
def test_h1_sin_limpieza_reproduce_el_borrador_previo(sin_limpieza):
    assert sin_limpieza["ventaneo"]["ventanas_generadas"] == 22_966
    assert sin_limpieza["ventaneo"]["ventanas_conservadas"] == 6_923
    assert sin_limpieza["filtrado"]["features_salida"] == 45

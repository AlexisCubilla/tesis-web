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


def test_una_perilla_que_la_tesis_no_nombra_tambien_cuenta():
    """El bug que esto fija, y por qué importa.

    `CONFIG_TESIS` sale de `tesis.config.CONFIG` y solo nombra los parámetros que el pipeline de la
    tesis tiene. El taller agrega perillas propias —hoy `filtrado.descartar`, que apaga el filtrado
    ENTERO— y la comparación recorría solo las claves de la referencia, así que una rama que saltea
    un paso que la tesis necesita respondía «cero diferencias».

    Eso no era cosmético: la hoja de Procedencia del Excel escribe «SÍ — coincide en todos los
    parámetros» a partir de esta cuenta, o sea que producía un archivo indistinguible del oficial
    sobre una corrida que no lo era, que es exactamente lo que el ADR A7 existe para evitar.

    `app.js` ya lo hacía bien (ver `esOficial`); la copia del backend se había quedado atrás.
    """
    dif = _diferencias_con_la_tesis(_cadena(filtrado={"descartar": False}))
    assert [(e, k) for e, k, _v, _r in dif] == [("filtrado", "descartar")]
    etapa, k, valor, esperado = dif[0]
    assert (valor, esperado) == (False, True), "el esperado es el `defecto` que declara la etapa"


def test_una_perilla_del_taller_en_su_valor_por_omision_no_es_una_diferencia():
    """El otro lado: `descartar=True` es lo que la tesis hace, aunque no lo nombre."""
    assert _diferencias_con_la_tesis(_cadena(filtrado={"descartar": True})) == []


def test_un_parametro_que_falta_en_el_nodo_cuenta_como_diferencia():
    """Recorrer la unión también cubre el caso inverso: la referencia lo nombra y el nodo no.

    Antes se recorrían los parámetros DEL NODO, así que un parámetro ausente simplemente no se
    miraba. Una rama a la que le falta un ajuste de la tesis no es la rama de la tesis.
    """
    cadena = _cadena()
    for nodo in cadena:
        if nodo["etapa"] == "ventaneo":
            nodo["parametros"].pop("tamano_ventana", None)
    dif = _diferencias_con_la_tesis(cadena)
    assert ("ventaneo", "tamano_ventana") in [(e, k) for e, k, _v, _r in dif]


# ---------------------------------------------------------------- la fecha de cada hoja

def test_la_fecha_de_una_hoja_sale_de_su_nombre():
    """`fecha_de_hoja` deriva la fecha del nombre, asumiendo 2021 cuando no lo dice.

    POR QUÉ EXISTE. El Excel no trae ninguna fecha absoluta: el tiempo que lleva es relativo al
    encendido y el GPS está en `#REF!`. El año de 40 de las 42 hojas es una INFERENCIA, apoyada en
    que BIRDS-4 se desplegó desde la ISS el 14 de marzo de 2021 (ver la nota de `ANIO_POR_OMISION`).
    Lo único que depende de ella es el orden en que se muestran las hojas, pero si se rompe en
    silencio la línea de tiempo cuenta la misión al revés y nada falla.
    """
    from backend import main

    assert main.fecha_de_hoja("March 28") == "2021-03-28"
    assert main.fecha_de_hoja("August 07") == "2021-08-07"
    assert main.fecha_de_hoja("May 6") == "2021-05-06", "un día sin cero adelante también"
    # Las dos que sí traen año son las que cruzan a 2022: el año escrito manda sobre el supuesto.
    assert main.fecha_de_hoja("January 02 2022") == "2022-01-02"
    assert main.fecha_de_hoja("January 24 2022") == "2022-01-24"


def test_las_hojas_que_no_son_fechas_no_inventan_una():
    """Las tres excluidas del estudio no tienen fecha, y devolver `None` es lo correcto.

    Inventarles una las mezclaría en el orden cronológico como si fueran un día de telemetría.
    """
    from backend import main

    for nombre in ("Anomalous data", "Test1 w batt", "Test2 wo batt", "", "Marzo 28"):
        assert main.fecha_de_hoja(nombre) is None, nombre


def test_ninguna_hoja_real_cae_antes_del_despliegue():
    """La comprobación que sostiene el supuesto de 2021.

    Si alguna de las hojas sin año fuera en realidad de otro año, lo más probable es que apareciera
    una fecha anterior al 14 de marzo de 2021 —el día en que el satélite salió de la ISS—, porque
    antes de eso no había telemetría que registrar. Que ninguna lo haga es lo que hace creíble la
    inferencia; si este test se rompe al cambiar de dataset, el supuesto hay que revisarlo.
    """
    import joblib
    import pytest

    from backend import almacen, main

    if not almacen.TABLA_CRUDA.exists():
        pytest.skip("hace falta la tabla cruda (mise run datos)")
    hojas = joblib.load(almacen.TABLA_CRUDA)["SheetName"].drop_duplicates()
    fechas = {h: main.fecha_de_hoja(str(h)) for h in hojas}
    sin_fecha = [h for h, f in fechas.items() if f is None]
    assert not sin_fecha, f"hojas cuyo nombre no es una fecha: {sin_fecha}"
    antes = [h for h, f in fechas.items() if f < "2021-03-14"]
    assert not antes, f"hojas anteriores al despliegue de BIRDS-4: {antes}"

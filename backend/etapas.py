"""Definición de las etapas del pipeline y sus envoltorios sobre el paquete `tesis`.

**Regla dura de este módulo:** acá NO se implementa lógica científica. Cada etapa arma un objeto de
configuración de `tesis` y llama a la función que corresponde. Si la web recalculara features o
consolidara eventos por su cuenta, tendríamos dos implementaciones que se separarían con el tiempo y el
sitio terminaría mostrando números distintos a los de la tesis.

Las etapas forman una cadena lineal. Cada una declara:
  - `parametros`: qué se puede configurar, con su tipo y rango (el frontend arma el formulario con esto)
  - `ejecutar(entrada, params)`: recibe la salida de la etapa anterior y devuelve (salida, resumen)
  - `resumen`: números chicos para mostrar en pantalla sin cargar el resultado completo
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Any, Callable

from . import ajustes


def _ref(etapa: str, nombre: str, respaldo: Any) -> Any:
    """Valor inicial de un parámetro: el de la configuración de referencia de la tesis.

    Antes estos números estaban escritos a mano acá **y** en la configuración de referencia, así que
    podían desincronizarse: cambiar el valor allá dejaba el formulario proponiendo el viejo. Ahora hay
    una sola fuente — `tesis.config.CONFIG`, vía `ajustes.config_tesis()` — y el formulario arranca
    siempre en la configuración con la que la tesis reporta sus resultados.

    El `respaldo` solo se usa para parámetros que no forman parte de esa configuración.
    """
    return ajustes.CONFIG_TESIS.get(etapa, {}).get(nombre, respaldo)

CADENA: tuple[str, ...] = (
    "datos",
    "ventaneo",
    "features",
    "filtrado",
    "deteccion",
    "eventos",
)


@dataclass(frozen=True)
class Parametro:
    """Un parámetro configurable de una etapa (el frontend arma el control con esto)."""

    nombre: str
    etiqueta: str
    tipo: str  # "entero" | "decimal" | "booleano" | "multiple"
    defecto: Any
    minimo: float | None = None
    maximo: float | None = None
    opciones: tuple[str, ...] | None = None
    ayuda: str = ""
    # Oculto como CONTROL, no como parámetro. Sigue existiendo, sigue teniendo su
    # defecto, sigue viajando en `defectos()` y sigue quedando registrado en los
    # parámetros del nodo —así el hash de la rama lo cubre y la ficha de la fase lo
    # muestra—. Lo único que no hace es aparecer en el formulario.
    #
    # Es para lo que define el estudio en lugar de configurarlo: si no hay una
    # pregunta de investigación que se responda cambiándolo, ofrecerlo solo invita a
    # producir una rama que no se puede comparar con nada.
    oculto: bool = False


@dataclass(frozen=True)
class Etapa:
    nombre: str
    titulo: str
    descripcion: str
    parametros: tuple[Parametro, ...]
    ejecutar: Callable[[Any, dict], tuple[Any, dict]]

    def defectos(self) -> dict[str, Any]:
        return {p.nombre: p.defecto for p in self.parametros}


# --------------------------------------------------------------------------------------
# Etapa 1 — datos: selección de hojas y limpieza
# --------------------------------------------------------------------------------------

def _ejecutar_datos(entrada, params):
    """Filtra hojas y (opcionalmente) limpia. La entrada es la tabla cruda precalculada.

    IMPORTANTE: la tabla cruda debe conservar el índice original del Excel. `preprocessing.clean`
    detecta los segmentos contiguos buscando saltos en ese índice; si se pierde, los segmentos salen
    mal **sin dar error**. Por eso el caché usa joblib y no CSV.

    Con `limpiar=False` no hay columna `segment`, así que el ventaneo agrupa por hoja. Ese camino
    reproduce el del trabajo previo a esta reconstrucción (documentado como hallazgo H1 en la tesis).
    """
    from tesis import preprocessing
    from tesis.config import CONFIG

    df = entrada
    excluidas = set(params.get("hojas_excluidas") or ())
    if excluidas:
        df = df[~df[CONFIG.data.group_column].isin(excluidas)]

    filas_antes = len(df)
    if params.get("limpiar", True):
        df = preprocessing.clean(df, CONFIG.data)
        segmentos = int(df[preprocessing.SEGMENT_COLUMN].nunique())
    else:
        df = df.reset_index(drop=False)  # conserva el índice original como columna, por trazabilidad
        df = df.set_index("index")
        segmentos = 0

    resumen = {
        "filas_entrada": int(filas_antes),
        "filas_salida": int(len(df)),
        "filas_descartadas": int(filas_antes - len(df)),
        "hojas": int(df[CONFIG.data.group_column].nunique()),
        "segmentos": segmentos,
        "limpieza": bool(params.get("limpiar", True)),
    }
    return df, resumen


ETAPA_DATOS = Etapa(
    nombre="datos",
    titulo="Datos",
    descripcion=(
        "Punto de partida: la telemetría del satélite, una medición cada 10-11 segundos, repartida en "
        "45 hojas del Excel original (cada hoja es una sesión de descarga distinta). Entran 42. Dos de "
        "las que quedan afuera son pruebas hechas en el laboratorio y no en vuelo. La tercera se llama "
        "'Anomalous data' y parecía ser el dato ideal para validar, pero al decodificar sus paquetes se "
        "vio que corresponde a una anomalía de los paneles solares y no de la batería: es otro problema, "
        "de otra investigación. Las tres quedan afuera por definición del estudio y no por "
        "configuración, así que no hay nada que elegir ahí. Lo que sí se elige acá es si se descartan "
        "las filas inválidas."
    ),
    parametros=(
        Parametro(
            "limpiar", "Descartar filas inválidas", "booleano", _ref("datos", "limpiar", True),
            ayuda="Hay 886 filas sin datos o con las tres señales exactamente en cero: son huecos del "
                  "programa que decodifica la telemetría, no mediciones reales. Al descartarlas, "
                  "además se marca dónde quedó un corte, para que después ninguna ventana de análisis "
                  "una dos tramos separados en el tiempo. "
                  "APAGARLO SIRVE PARA VER ALGO IMPORTANTE: en el trabajo previo a esta "
                  "reconstrucción no se limpiaba, y eso hacía que uno de los detectores "
                  "(HDBSCAN-GLOSH) pareciera poco confiable —marcaba ventanas distintas cada vez que "
                  "se le cambiaba la muestra—. Con los datos limpios resulta estable: aquella "
                  "conclusión era un efecto de las filas basura. (Hallazgo H1 de la tesis.)",
        ),
        Parametro(
            "hojas_excluidas", "Hojas que NO entran", "multiple",
            tuple(_ref("datos", "hojas_excluidas", ("Test1 w batt", "Test2 wo batt", "Anomalous data"))),
            oculto=True,
            ayuda="Dos son pruebas de laboratorio, no de vuelo. La tercera, 'Anomalous data', resultó "
                  "ser una anomalía de paneles solares y no de batería. Las tres quedan afuera por "
                  "definición del estudio: se registran acá, pero no se ofrecen como opción.",
        ),
    ),
    ejecutar=_ejecutar_datos,
)


# --------------------------------------------------------------------------------------
# Etapa 2 — ventaneo (+ deduplicación)
# --------------------------------------------------------------------------------------

def _ejecutar_ventaneo(entrada, params):
    """Ventanas deslizantes por tramo contiguo, y deduplicación opcional por coseno."""
    from tesis import preprocessing, windowing
    from tesis.config import CONFIG

    cfg = dataclasses.replace(
        CONFIG.window,
        window_size=int(params["tamano_ventana"]),
        stride=int(params["paso"]),
        use_dedup=bool(params["deduplicar"]),
        dedup_threshold=float(params["umbral_dedup"]),
    )
    ventanas = windowing.make_windows(entrada, cfg, segment_column=preprocessing.SEGMENT_COLUMN)
    aplanado = windowing.flatten_windows(ventanas)
    antes = len(ventanas)

    if cfg.use_dedup:
        conservadas = windowing.deduplicate_indices(aplanado, cfg)
        ventanas = windowing.subset_windows(ventanas, conservadas)
        aplanado = aplanado.iloc[conservadas].reset_index(drop=True)

    salida = {
        "ventanas": ventanas,
        "aplanado": aplanado,
        "meta": windowing.window_metadata(ventanas),
        "tamano_ventana": cfg.window_size,
    }
    resumen = {
        "ventanas_generadas": int(antes),
        "ventanas_conservadas": int(len(ventanas)),
        "eliminadas_por_dedup": int(antes - len(ventanas)),
        "reduccion_pct": round((antes - len(ventanas)) / antes * 100, 1) if antes else 0.0,
        "forma_tensor": list(ventanas.values.shape),
    }
    return salida, resumen


ETAPA_VENTANEO = Etapa(
    nombre="ventaneo",
    titulo="Ventaneo",
    descripcion=(
        "Una falla de batería no es un valor suelto fuera de rango: es un comportamiento a lo largo "
        "del tiempo. Por eso no se analiza fila por fila, sino en tramos de varias mediciones "
        "consecutivas que se van deslizando sobre la señal, como una lupa que recorre el registro. "
        "Cada tramo pasa a ser una unidad de análisis."
    ),
    parametros=(
        Parametro("tamano_ventana", "Mediciones por tramo", "entero",
                  _ref("ventaneo", "tamano_ventana", 50), 10, 500,
                  ayuda="Cuántas mediciones consecutivas mira cada tramo. Con 50 son unos 9 minutos de "
                        "telemetría. Como referencia: el satélite tarda unos 87 minutos en dar una "
                        "vuelta a la Tierra (medido en estos mismos datos), y en cada vuelta la batería "
                        "se carga al sol y se descarga en la sombra. Un tramo de 50 ve cerca del 10 % "
                        "de ese ciclo."),
        Parametro("paso", "Cada cuánto avanza el tramo", "entero",
                  _ref("ventaneo", "paso", 1), 1, 100,
                  ayuda="Con paso 1, el tramo avanza de a una medición: dos tramos vecinos comparten 49 "
                        "de sus 50 datos. Eso garantiza que nada se escape entre dos tramos, pero genera "
                        "mucha repetición — y de ahí salen los dos pasos que siguen. Con paso 5, los "
                        "tramos se pisan menos y hay menos que analizar."),
        Parametro("deduplicar", "Descartar tramos casi idénticos", "booleano",
                  _ref("ventaneo", "deduplicar", True),
                  ayuda="Compara los tramos entre sí y conserva uno solo de cada grupo de casi "
                        "iguales. Reduce el volumen alrededor de un 70 %. Tiene un costo conocido: la "
                        "comparación mira la FORMA de la señal y no su MAGNITUD, así que un tramo con "
                        "valores anormalmente altos pero de forma parecida a uno normal puede quedar "
                        "descartado. Es una decisión metodológica tomada por la tutoría de la tesis, "
                        "con esa limitación documentada."),
        Parametro("umbral_dedup", "Qué tan parecidos para descartar", "decimal",
                  _ref("ventaneo", "umbral_dedup", 0.95), 0.80, 0.999,
                  ayuda="Va de 0 a 1: 1 significa idénticos. Con 0,95 se descarta un tramo si se parece "
                        "en un 95 % o más a otro ya conservado. Subirlo (0,97) conserva más tramos; "
                        "bajarlo descarta más."),
    ),
    ejecutar=_ejecutar_ventaneo,
)


# --------------------------------------------------------------------------------------
# Etapa 3 — features
# --------------------------------------------------------------------------------------

def _ejecutar_features(entrada, params):
    """24 características por señal: estadísticas, temporales, autocorrelación y espectrales."""
    from tesis import features as mod_features
    from tesis.config import CONFIG

    lags = tuple(range(1, int(params["rezagos_autocorr"]) + 1))
    cfg = dataclasses.replace(CONFIG.features, autocorr_lags=lags)
    tabla = mod_features.extract_features(entrada["aplanado"], cfg)

    salida = {"features": tabla, "meta": entrada["meta"], "ventanas": entrada["ventanas"],
              "tamano_ventana": entrada["tamano_ventana"]}
    resumen = {
        "filas": int(tabla.shape[0]),
        "features": int(tabla.shape[1] - 1),  # menos la columna de hoja
        "rezagos": len(lags),
    }
    return salida, resumen


ETAPA_FEATURES = Etapa(
    nombre="features",
    titulo="Características",
    descripcion=(
        "Un tramo son 150 números sueltos (50 mediciones × 3 señales), difíciles de comparar entre sí. "
        "Acá cada tramo se resume en 24 números por señal que describen su comportamiento: cuánto vale "
        "y cuánto varía, si sube o baja, qué tan predecible es y qué tan rápido oscila. Es como "
        "describir una canción por su tempo, su volumen y qué tan aguda es, sin reproducirla."
    ),
    parametros=(
        Parametro("rezagos_autocorr", "Qué tan lejos se compara la señal consigo misma", "entero",
                  _ref("features", "rezagos_autocorr", 5), 1, 20,
                  ayuda="Mide si el valor de ahora permite predecir el de 1, 2, 3… mediciones después. "
                        "Una señal suave se parece mucho a sí misma; una errática, poco. Con 5 se "
                        "calculan cinco de esas comparaciones por señal."),
    ),
    ejecutar=_ejecutar_features,
)


# --------------------------------------------------------------------------------------
# Etapa 4 — filtrado
# --------------------------------------------------------------------------------------

def config_filtrado(params) -> "FilterConfig":  # noqa: F821
    """La configuración del filtrado a partir de los parámetros de un nodo.

    EXISTE PARA QUE HAYA UN SOLO LUGAR. La ejecución la usa para filtrar, y la
    pantalla de análisis la usa para reconstruir POR QUÉ se descartó cada
    característica —volviendo a correr el primer filtro por separado—. Si las dos
    armaran la config por su cuenta, alcanzaría con que una cambiara para que el
    gráfico de motivos empezara a mentir: seguiría pareciendo correcto y diría que
    se descartó algo que no se descartó. Ese es exactamente el modo de falla que el
    ADR A1 quiere evitar, y la forma de evitarlo no es un comentario pidiendo
    cuidado, es que la función sea una sola.

    Con `descartar=False` devuelve una config NEUTRA: no descarta nada y sigue
    estandarizando. Los tres valores neutros son deliberados y cada uno apaga un
    camino distinto de descarte:

      lowvar_percentile = 0     apaga el corte por percentil de IQR
      iqr_min           = 0     apaga el piso absoluto de IQR, que se aplica
                                SIEMPRE y aparte del percentil (ver
                                `filter_low_variance`): sin esto, «no descartar»
                                seguiría descartando las casi constantes
      correlation_threshold = 1.0001   ninguna correlación absoluta puede alcanzarlo,
                                así que no cae ningún par redundante

    Queda un caso que sí se descarta igual: una característica cuyo IQR sea NaN
    —una columna entera sin datos—, porque `NaN >= 0` es falso. No tiene arreglo
    desde acá y tampoco convendría: una columna así no se puede estandarizar.
    """
    from tesis.config import CONFIG

    base = CONFIG.filtering
    if not params.get("descartar", True):
        return dataclasses.replace(
            base, lowvar_percentile=0.0, iqr_min=0.0, correlation_threshold=1.0001,
        )
    return dataclasses.replace(
        base,
        correlation_threshold=float(params["umbral_correlacion"]),
        lowvar_percentile=float(params["percentil_baja_var"]),
    )


def _ejecutar_filtrado(entrada, params):
    """Descarta features de baja variabilidad y redundantes, y estandariza las que quedan.

    Con `descartar=False` no descarta ninguna, pero SÍ estandariza. Esa separación es
    el punto de la opción: el paso hace dos trabajos, y solo uno de los dos es el que
    se quiere poder apagar. Ver la nota de `config_filtrado`.
    """
    from tesis import filtering

    cfg = config_filtrado(params)
    antes = entrada["features"].shape[1] - 1
    tabla, _escalador = filtering.filter_and_scale(entrada["features"], cfg)

    salida = dict(entrada)
    salida["filtradas"] = tabla
    resumen = {
        "features_entrada": int(antes),
        "features_salida": int(tabla.shape[1] - 1),
        "descartadas": int(antes - (tabla.shape[1] - 1)),
    }
    return salida, resumen


ETAPA_FILTRADO = Etapa(
    nombre="filtrado",
    titulo="Filtrado",
    descripcion=(
        "Este paso hace DOS cosas, y conviene tenerlas separadas. Primero descarta características: las "
        "que dan casi siempre el mismo valor (no informan nada) y las que suben y bajan junto con otra "
        "(dicen lo mismo dos veces). Después lleva las que quedan a una escala común, para que ninguna "
        "pese más solo porque sus números son más grandes. El descarte se puede apagar; la escala "
        "común, no —PCA y HDBSCAN-GLOSH la necesitan, y sin ella el paso 5 cambiaría por un motivo que "
        "no tiene nada que ver con el filtrado."
    ),
    parametros=(
        Parametro(
            "descartar", "Descartar características", "booleano", True,
            ayuda="Apagarlo deja pasar las 72 al paso 5, estandarizadas igual. Sirve para responder "
                  "una pregunta concreta: ¿el filtrado mejora la detección, o solo la abarata? "
                  "Los dos umbrales de abajo quedan sin efecto cuando está apagado, y el paso sigue "
                  "existiendo en la rama con «sin descartar» anotado, así que la decisión queda "
                  "registrada en lugar de perderse.",
        ),
        Parametro("umbral_correlacion", "Cuándo dos características son redundantes", "decimal",
                  _ref("filtrado", "umbral_correlacion", 0.95), 0.5, 0.999,
                  ayuda="Va de 0 a 1. Si dos características se mueven juntas por encima de este valor, "
                        "se conserva solo una. Con 0,95 hay que ser casi idénticas; bajarlo descarta "
                        "más agresivamente."),
        Parametro("percentil_baja_var", "Cuánto descartar por poco variable", "decimal",
                  _ref("filtrado", "percentil_baja_var", 5.0), 0.0, 50.0,
                  ayuda="Descarta el porcentaje indicado de características, empezando por las que "
                        "menos varían entre tramos. Con 5 se saca el 5 % más plano. Poner 0 desactiva "
                        "este filtro."),
    ),
    ejecutar=_ejecutar_filtrado,
)


# --------------------------------------------------------------------------------------
# Etapa 5 — detección
# --------------------------------------------------------------------------------------

DETECTORES = ("isolation_forest", "ecod", "copod", "pca", "hdbscan_glosh")


def _ejecutar_deteccion(entrada, params):
    """Corre los detectores seleccionados. Convención: mayor score = más anómalo."""
    from tesis import detection
    from tesis.config import CONFIG

    elegidos = tuple(params["detectores"]) or DETECTORES
    cfg = dataclasses.replace(
        CONFIG.detection,
        detectors=elegidos,
        iforest_n_estimators=int(params["arboles_iforest"]),
        hdbscan_min_cluster_size=int(params["min_cluster_hdbscan"]),
    )
    scores = detection.run_detectors(entrada["filtradas"], cfg)

    salida = dict(entrada)
    salida["scores"] = scores
    resumen = {
        "detectores": list(elegidos),
        "ventanas_puntuadas": int(scores.shape[0]),
        # Los scores NO son comparables entre detectores: cada uno tiene su propia escala.
        "rango_por_detector": {c: [float(scores[c].min()), float(scores[c].max())] for c in scores},
    }
    return salida, resumen


ETAPA_DETECCION = Etapa(
    nombre="deteccion",
    titulo="Detección",
    descripcion=(
        "Acá se busca lo raro. Nadie etiquetó nunca estos datos, así que no hay forma de saber qué "
        "método acierta: por eso se usan cinco a la vez, cada uno con una idea distinta de qué "
        "significa 'raro'. Ninguno decide si algo es una anomalía — solo le ponen un puntaje a cada "
        "tramo y lo ordenan. Que cinco métodos que piensan diferente coincidan en el mismo tramo es lo "
        "que reemplaza a la respuesta correcta que no existe."
    ),
    parametros=(
        Parametro("detectores", "Qué métodos usar", "multiple",
                  tuple(_ref("deteccion", "detectores", DETECTORES)), opciones=DETECTORES,
                  ayuda="isolation_forest: lo raro se separa del resto con pocos cortes al azar. "
                        "ecod y copod: lo raro está en los extremos de la distribución. "
                        "pca: lo raro no se puede reconstruir con el patrón general de los datos. "
                        "hdbscan_glosh: lo raro está donde hay poca compañía, en zonas vacías. "
                        "Sacar alguno permite ver cuánto depende el resultado de ese método."),
        Parametro("arboles_iforest", "Cuántos árboles usa isolation_forest", "entero",
                  _ref("deteccion", "arboles_iforest", 300), 50, 1000,
                  ayuda="Ese método hace muchos cortes al azar y promedia. Más árboles = resultado más "
                        "estable, pero más lento. Con 300 alcanza para que no cambie entre corridas."),
        Parametro("min_cluster_hdbscan", "Grupo mínimo para hdbscan_glosh", "entero",
                  _ref("deteccion", "min_cluster_hdbscan", 15), 2, 100,
                  ayuda="Ese método busca zonas densas de tramos parecidos; este número dice cuántos "
                        "tramos hacen falta para considerar que hay un grupo. Más chico = grupos más "
                        "finos y más tramos quedan marcados como aislados."),
    ),
    ejecutar=_ejecutar_deteccion,
)


# --------------------------------------------------------------------------------------
# Etapa 6 — eventos (el entregable)
# --------------------------------------------------------------------------------------

def _ejecutar_eventos(entrada, params):
    """Selecciona los candidatos y consolida las ventanas solapadas en eventos."""
    from tesis import export
    from tesis.config import CONFIG

    cfg = dataclasses.replace(
        CONFIG.detection,
        detectors=tuple(entrada["scores"].columns),
        candidate_fraction=float(params["fraccion_candidatos"]),
        max_event_windows=(int(params["max_ventanas_evento"])
                           if params["max_ventanas_evento"] else None),
    )
    tabla = export.build_candidate_table(
        entrada["scores"], entrada["meta"],
        features=entrada["filtradas"], detection_cfg=cfg,
        window_size=entrada["tamano_ventana"],
    )

    salida = dict(entrada)
    salida["eventos"] = tabla
    n = len(tabla)
    resumen = {
        "eventos": int(n),
        "ventanas_candidatas": int(tabla["n_ventanas"].sum()) if n else 0,
        "eventos_una_ventana": int((tabla["n_ventanas"] == 1).sum()) if n else 0,
        "en_el_limite": (int((tabla["n_ventanas"] == cfg.max_event_windows).sum())
                         if n and cfg.max_event_windows else 0),
        "por_prioridad": ({int(k): int(v) for k, v in
                           tabla["n_detectores"].value_counts().sort_index(ascending=False).items()}
                          if n else {}),
        "alta_prioridad": int((tabla["n_detectores"] >= 4).sum()) if n else 0,
    }
    return salida, resumen


ETAPA_EVENTOS = Etapa(
    nombre="eventos",
    titulo="Eventos candidatos",
    descripcion=(
        "El resultado final. De todos los tramos puntuados se toman los más raros, y los que se pisan "
        "en el tiempo se juntan en un solo EVENTO: una misma anomalía aparece marcada en muchos tramos "
        "vecinos, y mostrarlos por separado sería repetir veinte veces el mismo hecho. Cada evento "
        "queda con su momento, cuántos métodos lo señalaron y qué características se desviaron. Esta "
        "es la lista que después revisa una persona experta."
    ),
    parametros=(
        Parametro("fraccion_candidatos", "Qué proporción se marca como sospechosa", "decimal",
                  _ref("eventos", "fraccion_candidatos", 0.01), 0.001, 0.20,
                  ayuda="0,01 significa que cada método señala el 1 % de tramos con puntaje más alto. "
                        "OJO: esto NO afirma que el 1 % de los datos sean anomalías. Es un presupuesto "
                        "de revisión — cuántos casos puede mirar una persona en un rato razonable. "
                        "Subirlo a 0,05 da más candidatos y, en estos datos, más casos donde varios "
                        "métodos coinciden."),
        Parametro("max_ventanas_evento", "Tope de tramos por evento", "entero",
                  _ref("eventos", "max_ventanas_evento", 15), 0, 200,
                  ayuda="Corta los eventos muy largos. Poner 0 los deja crecer sin límite. "
                        "CUIDADO AL INTERPRETARLO: cuando un evento llega al tope, el resto se "
                        "convierte en un evento aparte que en realidad es la continuación del anterior "
                        "y se superpone con él. Eso infla el conteo de eventos y puede hacer parecer "
                        "que hay más hallazgos de los que hay."),
    ),
    ejecutar=_ejecutar_eventos,
)


REGISTRO: dict[str, Etapa] = {
    e.nombre: e for e in (
        ETAPA_DATOS, ETAPA_VENTANEO, ETAPA_FEATURES,
        ETAPA_FILTRADO, ETAPA_DETECCION, ETAPA_EVENTOS,
    )
}


def etapa_siguiente(nombre: str | None) -> str | None:
    """Devuelve la etapa que sigue en la cadena (o la primera si `nombre` es None)."""
    if nombre is None:
        return CADENA[0]
    i = CADENA.index(nombre)
    return CADENA[i + 1] if i + 1 < len(CADENA) else None


def descripcion_serializable() -> list[dict]:
    """Las etapas en formato JSON, para que el frontend arme los formularios."""
    salida = []
    for nombre in CADENA:
        e = REGISTRO[nombre]
        salida.append({
            "nombre": e.nombre,
            "titulo": e.titulo,
            "descripcion": e.descripcion,
            "parametros": [dataclasses.asdict(p) for p in e.parametros],
        })
    return salida

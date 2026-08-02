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
        "45 hojas del Excel original (cada hoja es una sesión de descarga distinta). Acá se elige qué "
        "hojas entran al estudio y si se descartan las filas inválidas."
    ),
    parametros=(
        Parametro(
            "limpiar", "Descartar filas inválidas", "booleano", True,
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
            ("Test1 w batt", "Test2 wo batt", "Anomalous data"),
            ayuda="Las dos primeras son pruebas hechas en el laboratorio, no en vuelo. La tercera se "
                  "llama 'Anomalous data' y parecía ser el dato ideal para validar, pero al decodificar "
                  "sus paquetes se vio que corresponde a una anomalía de los paneles solares, no de la "
                  "batería: es otro problema.",
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
        Parametro("tamano_ventana", "Mediciones por tramo", "entero", 50, 10, 500,
                  ayuda="Cuántas mediciones consecutivas mira cada tramo. Con 50 son unos 9 minutos de "
                        "telemetría. Como referencia: el satélite tarda unos 87 minutos en dar una "
                        "vuelta a la Tierra (medido en estos mismos datos), y en cada vuelta la batería "
                        "se carga al sol y se descarga en la sombra. Un tramo de 50 ve cerca del 10 % "
                        "de ese ciclo."),
        Parametro("paso", "Cada cuánto avanza el tramo", "entero", 1, 1, 100,
                  ayuda="Con paso 1, el tramo avanza de a una medición: dos tramos vecinos comparten 49 "
                        "de sus 50 datos. Eso garantiza que nada se escape entre dos tramos, pero genera "
                        "mucha repetición — y de ahí salen los dos pasos que siguen. Con paso 5, los "
                        "tramos se pisan menos y hay menos que analizar."),
        Parametro("deduplicar", "Descartar tramos casi idénticos", "booleano", True,
                  ayuda="Compara los tramos entre sí y conserva uno solo de cada grupo de casi "
                        "iguales. Reduce el volumen alrededor de un 70 %. Tiene un costo conocido: la "
                        "comparación mira la FORMA de la señal y no su MAGNITUD, así que un tramo con "
                        "valores anormalmente altos pero de forma parecida a uno normal puede quedar "
                        "descartado. Es una decisión metodológica tomada por la tutoría de la tesis, "
                        "con esa limitación documentada."),
        Parametro("umbral_dedup", "Qué tan parecidos para descartar", "decimal", 0.95, 0.80, 0.999,
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
                  5, 1, 20,
                  ayuda="Mide si el valor de ahora permite predecir el de 1, 2, 3… mediciones después. "
                        "Una señal suave se parece mucho a sí misma; una errática, poco. Con 5 se "
                        "calculan cinco de esas comparaciones por señal."),
    ),
    ejecutar=_ejecutar_features,
)


# --------------------------------------------------------------------------------------
# Etapa 4 — filtrado
# --------------------------------------------------------------------------------------

def _ejecutar_filtrado(entrada, params):
    """Descarta features de baja variabilidad y redundantes, y estandariza las que quedan."""
    from tesis import filtering
    from tesis.config import CONFIG

    cfg = dataclasses.replace(
        CONFIG.filtering,
        correlation_threshold=float(params["umbral_correlacion"]),
        lowvar_percentile=float(params["percentil_baja_var"]),
    )
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
        "De las 72 características calculadas, muchas no sirven para distinguir un tramo de otro. Acá "
        "se descartan dos tipos: las que dan casi siempre el mismo valor (no informan nada) y las que "
        "suben y bajan junto con otra (dicen lo mismo dos veces). Las que quedan se llevan a una escala "
        "común, para que ninguna pese más solo porque sus números son más grandes."
    ),
    parametros=(
        Parametro("umbral_correlacion", "Cuándo dos características son redundantes", "decimal",
                  0.95, 0.5, 0.999,
                  ayuda="Va de 0 a 1. Si dos características se mueven juntas por encima de este valor, "
                        "se conserva solo una. Con 0,95 hay que ser casi idénticas; bajarlo descarta "
                        "más agresivamente."),
        Parametro("percentil_baja_var", "Cuánto descartar por poco variable", "decimal",
                  5.0, 0.0, 50.0,
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
        Parametro("detectores", "Qué métodos usar", "multiple", DETECTORES, opciones=DETECTORES,
                  ayuda="isolation_forest: lo raro se separa del resto con pocos cortes al azar. "
                        "ecod y copod: lo raro está en los extremos de la distribución. "
                        "pca: lo raro no se puede reconstruir con el patrón general de los datos. "
                        "hdbscan_glosh: lo raro está donde hay poca compañía, en zonas vacías. "
                        "Sacar alguno permite ver cuánto depende el resultado de ese método."),
        Parametro("arboles_iforest", "Cuántos árboles usa isolation_forest", "entero", 300, 50, 1000,
                  ayuda="Ese método hace muchos cortes al azar y promedia. Más árboles = resultado más "
                        "estable, pero más lento. Con 300 alcanza para que no cambie entre corridas."),
        Parametro("min_cluster_hdbscan", "Grupo mínimo para hdbscan_glosh", "entero", 15, 2, 100,
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
                  0.01, 0.001, 0.20,
                  ayuda="0,01 significa que cada método señala el 1 % de tramos con puntaje más alto. "
                        "OJO: esto NO afirma que el 1 % de los datos sean anomalías. Es un presupuesto "
                        "de revisión — cuántos casos puede mirar una persona en un rato razonable. "
                        "Subirlo a 0,05 da más candidatos y, en estos datos, más casos donde varios "
                        "métodos coinciden."),
        Parametro("max_ventanas_evento", "Tope de tramos por evento", "entero", 15, 0, 200,
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

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

    Con `limpiar=False` se reproduce el camino del borrador previo (ver hallazgo H1 de la tesis):
    no hay columna `segment`, así que el ventaneo agrupa por hoja.
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
        "Elige qué hojas del Excel entran al estudio y si se aplica la limpieza (descartar filas con "
        "datos faltantes o con las tres señales en cero). Apagar la limpieza reproduce el camino del "
        "borrador previo: es el interruptor del hallazgo H1."
    ),
    parametros=(
        Parametro(
            "limpiar", "Aplicar limpieza", "booleano", True,
            ayuda="Descarta filas inválidas y marca los tramos contiguos. Apagarlo reproduce H1.",
        ),
        Parametro(
            "hojas_excluidas", "Hojas excluidas", "multiple",
            ("Test1 w batt", "Test2 wo batt", "Anomalous data"),
            ayuda="Por defecto se excluyen las dos de laboratorio y 'Anomalous data' (anomalía de "
                  "paneles, no de batería).",
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
        "Corta la telemetría en ventanas deslizantes. Una anomalía es un comportamiento en el tiempo, "
        "no un valor suelto. El paso indica cada cuántas muestras avanza la ventana: con paso 1 dos "
        "ventanas vecinas comparten casi todos sus datos, y de esa redundancia nacen la deduplicación "
        "y la consolidación en eventos."
    ),
    parametros=(
        Parametro("tamano_ventana", "Tamaño de ventana (muestras)", "entero", 50, 10, 500,
                  ayuda="50 muestras ≈ 9 minutos. El ciclo de carga/descarga del satélite dura ~490."),
        Parametro("paso", "Paso (stride)", "entero", 1, 1, 100,
                  ayuda="Cada cuántas muestras avanza la ventana."),
        Parametro("deduplicar", "Deduplicar ventanas", "booleano", True,
                  ayuda="Descarta ventanas casi idénticas por similitud coseno (ADR-0008)."),
        Parametro("umbral_dedup", "Umbral de deduplicación", "decimal", 0.95, 0.80, 0.999,
                  ayuda="Más alto = se conservan más ventanas."),
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
        "Resume cada ventana en números que describen su comportamiento: cuánto vale y cuánto varía, "
        "hacia dónde va, cuánto se parece a sí misma y cuál es su ritmo. Es como describir una canción "
        "por su tempo y su volumen sin reproducirla."
    ),
    parametros=(
        Parametro("rezagos_autocorr", "Rezagos de autocorrelación", "entero", 5, 1, 20,
                  ayuda="Cuántos pasos hacia adelante se compara la señal consigo misma."),
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
        "Saca las características que no aportan: las que casi no cambian entre ventanas (no "
        "distinguen nada) y las que dicen lo mismo que otra. Después estandariza las que quedan, "
        "para que ninguna pese más solo por estar en unidades más grandes."
    ),
    parametros=(
        Parametro("umbral_correlacion", "Umbral de correlación (Spearman)", "decimal", 0.95, 0.5, 0.999,
                  ayuda="Si dos features correlacionan por encima de esto, se descarta una."),
        Parametro("percentil_baja_var", "Percentil de baja variabilidad", "decimal", 5.0, 0.0, 50.0,
                  ayuda="Descarta el percentil inferior por rango intercuartílico. 0 lo desactiva."),
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
        "Cinco algoritmos con nociones distintas de 'raro' le ponen un puntaje a cada ventana. Ninguno "
        "decide qué es una anomalía: solo ordenan. Como no hay etiquetas de referencia, el acuerdo "
        "entre métodos de familias distintas reemplaza a la métrica de acierto."
    ),
    parametros=(
        Parametro("detectores", "Detectores", "multiple", DETECTORES, opciones=DETECTORES,
                  ayuda="Cuáles de los cinco se ejecutan."),
        Parametro("arboles_iforest", "Árboles (Isolation Forest)", "entero", 300, 50, 1000),
        Parametro("min_cluster_hdbscan", "Tamaño mínimo de cluster (HDBSCAN)", "entero", 15, 2, 100),
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
        "Toma la fracción superior de puntajes como candidatas y agrupa las que se solapan en el "
        "tiempo: una misma anomalía aparece marcada en muchas ventanas vecinas y se presenta como un "
        "solo evento. Esta es la salida que revisa el experto."
    ),
    parametros=(
        Parametro("fraccion_candidatos", "Fracción de candidatos", "decimal", 0.01, 0.001, 0.20,
                  ayuda="0,01 = el 1% más raro según cada detector. Es un presupuesto de revisión, "
                        "no una tasa real de anomalías."),
        Parametro("max_ventanas_evento", "Máx. ventanas por evento", "entero", 15, 0, 200,
                  ayuda="0 = sin límite. Al cortar, el resto del tramo forma un evento nuevo que se "
                        "solapa con el anterior."),
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

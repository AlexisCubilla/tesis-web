"""API del taller de experimentación y servidor de la web didáctica.

El backend es una capa delgada: recibe una configuración, arma los objetos de `tesis`, llama a la
etapa que corresponde y guarda el resultado con su hash. **Toda la lógica científica vive en el
paquete de la tesis** (ver `etapas.py`).
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import ajustes, almacen, etapas, trabajos

RAIZ = ajustes.RAIZ
WEB = ajustes.DIR_WEB

app = FastAPI(title="Taller — Etapa 1", version="0.1.0")
_con = almacen.conectar()
trabajos.iniciar_trabajador(_con)


class PeticionEjecutar(BaseModel):
    etapa: str
    padre: str | None = None
    parametros: dict = {}
    etiqueta: str | None = None


# --------------------------------------------------------------------------------------
# API
# --------------------------------------------------------------------------------------

@app.get("/api/etapas")
def get_etapas():
    """Las etapas con sus parámetros. El frontend arma los formularios a partir de esto."""
    return {"cadena": list(etapas.CADENA), "etapas": etapas.descripcion_serializable()}


@app.get("/api/estado")
def get_estado():
    """Estado general: si están los datos base, con qué versión de la tesis corre y su configuración."""
    try:
        import tesis

        version = tesis.__version__
    except Exception:
        version = None
    return {
        "datos_listos": almacen.TABLA_CRUDA.exists(),
        "commit_tesis": almacen.commit_tesis(),
        "version_tesis": version,
        "ruta_tesis": str(ajustes.ruta_tesis()),
        "nodos": len(almacen.listar(_con)),
        # La configuración de referencia se sirve desde el backend para que exista en un solo lugar
        # (`backend/ajustes.py`, ajustable por .env) y no duplicada en el frontend.
        "config_tesis": ajustes.CONFIG_TESIS,
        "origen_config": ajustes.origen_config(),
        "muestreo_segundos": ajustes.MUESTREO_SEGUNDOS,
    }


@app.get("/api/arbol")
def get_arbol():
    """Todos los nodos del árbol de ejecuciones."""
    return {"nodos": almacen.listar(_con)}


@app.post("/api/ejecutar")
def post_ejecutar(pet: PeticionEjecutar):
    """Crea (o recupera) un nodo y lo encola.

    Si la configuración ya se ejecutó antes, devuelve el nodo existente sin recalcular: es el caché
    por hash. Ramificar es simplemente pedir una etapa con otros parámetros sobre el mismo padre.
    """
    if pet.etapa not in etapas.REGISTRO:
        raise HTTPException(404, f"Etapa desconocida: {pet.etapa}")

    etapa = etapas.REGISTRO[pet.etapa]
    params = {**etapa.defectos(), **(pet.parametros or {})}
    params = {k: (tuple(v) if isinstance(v, list) else v) for k, v in params.items()}

    # Validación de la cadena: la etapa pedida debe seguir a la del padre.
    padre = almacen.obtener(_con, pet.padre) if pet.padre else None
    if pet.padre and padre is None:
        raise HTTPException(404, f"Nodo padre inexistente: {pet.padre}")
    esperada = etapas.etapa_siguiente(padre["etapa"] if padre else None)
    if pet.etapa != esperada:
        raise HTTPException(400, f"Después de {padre['etapa'] if padre else 'la raíz'} "
                                 f"corresponde '{esperada}', no '{pet.etapa}'")

    clave = almacen.clave_nodo(pet.etapa, params, pet.padre)
    existente = almacen.obtener(_con, clave)
    if existente and existente["estado"] == "listo" and existente["tiene_resultado"]:
        return {"clave": clave, "reutilizado": True, "nodo": existente}

    almacen.crear_nodo(_con, clave, pet.etapa, pet.padre, params, pet.etiqueta)
    trabajos.encolar(clave)
    return {"clave": clave, "reutilizado": False, "nodo": almacen.obtener(_con, clave)}


@app.get("/api/nodo/{clave}")
def get_nodo(clave: str):
    nodo = almacen.obtener(_con, clave)
    if nodo is None:
        raise HTTPException(404, "Nodo inexistente")
    nodo["cadena"] = almacen.cadena_hasta(_con, clave)
    return nodo


@app.delete("/api/nodo/{clave}")
def delete_nodo(clave: str):
    """Borra el nodo, todo lo que cuelga de él y sus resultados en disco."""
    if almacen.obtener(_con, clave) is None:
        raise HTTPException(404, "Nodo inexistente")
    return almacen.borrar(_con, clave)


#: Tope de puntos de una serie temporal antes de empezar a submuestrear. Ver `get_datos`.
SERIE_COMPLETA = 20_000


@app.get("/api/nodo/{clave}/datos")
def get_datos(clave: str, hoja: str | None = None, limite: int = 300):
    """Datos para inspeccionar una etapa. Siempre acotados: esto viaja al navegador."""
    import numpy as np

    nodo = almacen.obtener(_con, clave)
    if nodo is None:
        raise HTTPException(404, "Nodo inexistente")
    if nodo["estado"] != "listo" or not nodo["tiene_resultado"]:
        raise HTTPException(409, "El nodo todavía no tiene resultado")

    salida = almacen.cargar_resultado(clave)
    etapa = nodo["etapa"]
    grupo = "SheetName"

    # ---- Datos: la serie temporal real de una hoja -------------------------------------
    if etapa == "datos":
        hojas = salida[grupo].drop_duplicates().tolist()
        elegida = hoja if hoja in hojas else hojas[0]
        sub = salida[salida[grupo] == elegida]
        señales = [c for c in sub.columns if c not in (grupo, "segment")]
        # El gráfico deja acercarse a un tramo, y acercarse sobre una curva diezmada solo agranda
        # la diezma: no aparece ni un dato nuevo. Por eso la serie va entera. La hoja más grande
        # tiene ~1.100 mediciones × 3 señales, unas decenas de KB contra un servidor local; el
        # submuestreo queda solo como red de contención por si alguna vez hay una hoja enorme.
        paso = max(1, len(sub) // max(limite, SERIE_COMPLETA))
        sub = sub.iloc[::paso]
        return {
            "tipo": "serie",
            "hojas": hojas,
            "hoja": elegida,
            "senales": señales,
            "valores": [[None if pd_isna(v) else float(v) for v in fila]
                        for fila in sub[señales].to_numpy()],
            "por_hoja": salida.groupby(grupo).size().sort_values(ascending=False).head(20).to_dict(),
        }

    # ---- Ventaneo: ventanas de ejemplo dibujables --------------------------------------
    if etapa == "ventaneo":
        ventanas, meta = salida["ventanas"], salida["meta"]
        n = len(ventanas)
        indices = [0, n // 4, n // 2, (3 * n) // 4][:max(1, min(4, n))] if n else []
        ejemplos = []
        for i in indices:
            ejemplos.append({
                "pos": int(i),
                "hoja": str(meta.loc[i, grupo]),
                "inicio": int(meta.loc[i, "start"]),
                "valores": ventanas.values[i].tolist(),
            })
        return {
            "tipo": "ventanas",
            "senales": list(ventanas.signal_columns),
            "ejemplos": ejemplos,
            "por_hoja": meta.groupby(grupo).size().sort_values(ascending=False).head(20).to_dict(),
            "tamano": int(ventanas.values.shape[1]) if n else 0,
        }

    # ---- Características: qué se calculó, por familia ----------------------------------
    if etapa == "features":
        tabla = salida["features"]
        cols = [c for c in tabla.columns if c != grupo]
        por_senal: dict[str, list[str]] = {}
        for c in cols:
            señal = c.split("__")[0] if "__" in c else "otras"
            por_senal.setdefault(señal, []).append(c.split("__")[-1])
        return {"tipo": "features", "total": len(cols), "por_senal": por_senal}

    # ---- Filtrado: cuáles sobrevivieron y cuáles no ------------------------------------
    if etapa == "filtrado":
        antes = {c for c in salida["features"].columns if c != grupo}
        despues = {c for c in salida["filtradas"].columns if c != grupo}
        return {
            "tipo": "filtrado",
            "conservadas": sorted(despues),
            "descartadas": sorted(antes - despues),
        }

    # ---- Detección: distribución de puntajes y las ventanas más extremas ---------------
    if etapa == "deteccion":
        sc = salida["scores"]
        meta = salida["meta"]
        top = {}
        for c in sc.columns:
            idx = sc[c].nlargest(8).index
            top[c] = [{"pos": int(p), "hoja": str(meta.loc[p, grupo]),
                       "inicio": int(meta.loc[p, "start"]), "score": float(sc.loc[p, c])}
                      for p in idx]
        return {
            "tipo": "scores",
            "detectores": list(sc.columns),
            # Percentiles: cada detector tiene su escala, no son comparables entre sí.
            "percentiles": {c: [float(sc[c].quantile(q / 100)) for q in range(0, 101, 5)]
                            for c in sc.columns},
            "top": top,
        }

    # ---- Eventos: el entregable --------------------------------------------------------
    if etapa == "eventos":
        tabla = salida["eventos"]
        return {
            "tipo": "eventos",
            "columnas": list(tabla.columns),
            "filas": json.loads(tabla.head(limite).to_json(orient="records")),
        }

    return {"tipo": "desconocido"}


def pd_isna(v) -> bool:
    import pandas as pd

    return bool(pd.isna(v))


@app.get("/api/nodo/{clave}/analisis")
def get_analisis(clave: str, detector: str | None = None):
    """Datos para la pantalla de análisis: los cuatro cortes que el taller no mostraba.

    REGLA. Nada de esto redefine el pipeline (ADR A1). La selección de candidatos se le pide al
    propio paquete de la tesis —`export._detector_candidates`, la misma que usa
    `build_candidate_table`— justamente para no tener dos reglas de «qué tramo está marcado» que
    puedan separarse con el tiempo. Lo que se calcula acá es solo cómo mostrarlo: contar
    intersecciones, armar histogramas, correlacionar columnas y proyectar a dos dimensiones.

    La proyección 2D **es cálculo nuevo y es solo para mirar**: no alimenta ninguna etapa, no se
    guarda y ningún número de la tesis depende de ella. Se deja dicho para que no se confunda con
    el PCA que sí es un detector del pipeline.
    """
    import numpy as np
    import pandas as pd

    nodo = almacen.obtener(_con, clave)
    if nodo is None:
        raise HTTPException(404, "Nodo inexistente")
    if nodo["estado"] != "listo" or not nodo["tiene_resultado"]:
        raise HTTPException(409, "El nodo todavía no tiene resultado")

    salida = almacen.cargar_resultado(clave)
    if not isinstance(salida, dict) or "scores" not in salida:
        raise HTTPException(
            409, "El análisis necesita un paso de detección o posterior: ahí aparecen los puntajes"
        )

    scores: "pd.DataFrame" = salida["scores"]
    filtradas: "pd.DataFrame" = salida["filtradas"]
    detectores = list(scores.columns)
    n = int(len(scores))
    grupo = "SheetName"

    # ---- Coincidencia entre detectores -------------------------------------------------
    # `fraccion_candidatos` es un parámetro de la etapa de eventos; si se está mirando un nodo de
    # detección todavía no existe, así que se usa el valor de referencia de la tesis.
    fraccion = float(nodo["parametros"].get("fraccion_candidatos")
                     or ajustes.CONFIG_TESIS.get("eventos", {}).get("fraccion_candidatos", 0.01))

    from tesis import export
    from tesis.config import CONFIG

    cfg_det = dataclasses.replace(CONFIG.detection, detectors=tuple(detectores),
                                  candidate_fraction=fraccion)
    marcados = export._detector_candidates(scores, cfg_det)  # dict[detector] -> set de posiciones

    matriz = [[len(marcados[a] & marcados[b]) for b in detectores] for a in detectores]
    cuantos = pd.Series(0, index=scores.index, dtype=int)
    for d in detectores:
        cuantos.loc[list(marcados[d])] += 1
    reparto = {int(k): int(v) for k, v in cuantos[cuantos > 0].value_counts().sort_index().items()}

    # ---- Distribución de puntajes: histograma y caja ------------------------------------
    puntajes = {}
    for d in detectores:
        s = scores[d].to_numpy(dtype=float)
        s = s[np.isfinite(s)]
        cuentas, bordes = np.histogram(s, bins=40)
        q1, med, q3 = (float(np.quantile(s, q)) for q in (0.25, 0.5, 0.75))
        iqr = q3 - q1
        bajo, alto = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        dentro = s[(s >= bajo) & (s <= alto)]
        puntajes[d] = {
            "bordes": [float(x) for x in bordes],
            "cuentas": [int(x) for x in cuentas],
            "caja": [float(dentro.min()) if dentro.size else float(s.min()), q1, med, q3,
                     float(dentro.max()) if dentro.size else float(s.max())],
            "atipicos": int(((s < bajo) | (s > alto)).sum()),
            "corte": float(np.quantile(s, 1 - fraccion)),
        }

    # ---- Correlación entre características ----------------------------------------------
    # Se correlacionan las de ANTES del filtrado, marcando cuáles sobrevivieron: así el mapa
    # muestra *por qué* se descartó cada una, que es lo que la lista de pastillas no dice.
    previas: "pd.DataFrame" = salida.get("features", filtradas)
    cols_prev = [c for c in previas.columns if c != grupo]
    cols_prev.sort()  # el nombre es «señal__medida», así que ordenar agrupa por señal
    corr = previas[cols_prev].corr().fillna(0.0)
    conservadas = {c for c in filtradas.columns if c != grupo}

    # ---- Dispersión 2D de las ventanas ---------------------------------------------------
    elegido = detector if detector in detectores else detectores[0]
    cols_filt = [c for c in filtradas.columns if c != grupo]
    X = filtradas[cols_filt].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    centro = X.mean(axis=0)
    escala = X.std(axis=0)
    escala[escala == 0] = 1.0
    Z = (X - centro) / escala
    # SVD en vez de sklearn: son dos componentes y evita arrastrar una dependencia más para dibujar.
    U, S, _ = np.linalg.svd(Z, full_matrices=False)
    proy = U[:, :2] * S[:2]
    varianza = (S ** 2) / float((S ** 2).sum() or 1.0)

    marcado_elegido = marcados[elegido]
    meta = salida.get("meta")
    hojas = (meta[grupo].astype(str).tolist() if meta is not None and grupo in meta
             else [""] * n)

    return {
        "detectores": detectores,
        "detector": elegido,
        "n_ventanas": n,
        "fraccion_candidatos": fraccion,
        "top_k": int(np.ceil(n * fraccion)),
        "coincidencia": {"orden": detectores, "matriz": matriz, "reparto": reparto},
        "puntajes": puntajes,
        "correlacion": {
            "features": cols_prev,
            "matriz": [[round(float(v), 4) for v in fila] for fila in corr.to_numpy()],
            "conservadas": [c in conservadas for c in cols_prev],
        },
        "dispersion": {
            "x": [round(float(v), 4) for v in proy[:, 0]],
            "y": [round(float(v), 4) for v in proy[:, 1]],
            "puntaje": [round(float(v), 6) for v in scores[elegido].to_numpy(dtype=float)],
            "candidato": [bool(i in marcado_elegido) for i in range(n)],
            "hoja": hojas,
            "varianza_explicada": [round(float(varianza[0]), 4), round(float(varianza[1]), 4)],
        },
    }


@app.get("/api/nodo/{clave}/evento/{event_id}")
def get_evento(clave: str, event_id: int):
    """Las series crudas del tramo de un evento, para dibujarlo."""
    nodo = almacen.obtener(_con, clave)
    if nodo is None or nodo["etapa"] != "eventos" or not nodo["tiene_resultado"]:
        raise HTTPException(404, "No hay eventos en ese nodo")

    salida = almacen.cargar_resultado(clave)
    tabla = salida["eventos"]
    fila = tabla[tabla["event_id"] == event_id]
    if fila.empty:
        raise HTTPException(404, "Evento inexistente")
    fila = fila.iloc[0]

    ventanas = salida["ventanas"]
    meta = salida["meta"]
    posiciones = meta.index[(meta["segment"] == fila["segment"])
                            & (meta["start"] >= fila["start"])
                            & (meta["start"] < fila["end"])].tolist()
    if not posiciones:
        raise HTTPException(404, "Sin ventanas para el evento")

    import numpy as np

    largo = int(fila["end"] - fila["start"])
    señales = list(ventanas.signal_columns)
    acum = np.full((largo, len(señales)), np.nan)
    for p in posiciones:
        desde = int(meta.loc[p, "start"] - fila["start"])
        bloque = ventanas.values[p]
        # Una ventana que arranca cerca del final se extiende más allá del tramo del evento
        # (sobre todo con el límite de ventanas por evento activo): se recorta al rango.
        hasta = min(desde + bloque.shape[0], largo)
        if hasta > desde:
            acum[desde:hasta, :] = bloque[:hasta - desde, :]

    return {
        "evento": json.loads(fila.to_json()),
        "senales": señales,
        "valores": [[None if np.isnan(v) else float(v) for v in fila_v] for fila_v in acum],
    }


# --------------------------------------------------------------------------------------
# Web estática
# --------------------------------------------------------------------------------------

@app.middleware("http")
async def revalidar_el_frontend(request, call_next):
    """Obliga al navegador a preguntar siempre si el HTML/CSS/JS cambió.

    Sin esto, las respuestas del frontend salen con `etag` y `last-modified` pero **sin**
    `Cache-Control`. Ante esa combinación el navegador aplica «frescura heurística»: decide por su
    cuenta durante cuánto tiempo el archivo sigue vigente y lo sirve de su caché sin preguntar
    nada. El resultado es que editar `web/` y recargar dejaba media aplicación vieja — típicamente
    una pantalla con la versión nueva y la otra con la anterior, que es difícil de diagnosticar
    porque el servidor sí está entregando el archivo correcto.

    Eso choca de frente con que el frontend se monte en el contenedor justamente para poder
    editarlo sin reconstruir la imagen.

    `no-cache` no prohíbe guardar: obliga a revalidar. Para `/estatico/*` eso sale gratis, porque
    StaticFiles contesta 304 vacío ante el `etag`. Las dos rutas de HTML reenvían el cuerpo entero
    (unos 30 KB entre las dos, contra un servidor que corre en la misma máquina): se prefiere eso
    antes que volver a tener pantallas desincronizadas.

    La API queda afuera: sus respuestas son dinámicas y ya nadie las cachea.
    """
    respuesta = await call_next(request)
    if not request.url.path.startswith("/api/"):
        respuesta.headers["Cache-Control"] = "no-cache"
    return respuesta


@app.get("/")
def raiz():
    return FileResponse(WEB / "index.html")


@app.get("/analisis")
def analisis():
    return FileResponse(WEB / "analisis.html")


@app.get("/taller")
def taller():
    return FileResponse(WEB / "taller.html")


app.mount("/estatico", StaticFiles(directory=WEB), name="estatico")

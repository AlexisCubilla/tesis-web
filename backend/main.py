"""API del taller de experimentación y servidor de la web didáctica.

El backend es una capa delgada: recibe una configuración, arma los objetos de `tesis`, llama a la
etapa que corresponde y guarda el resultado con su hash. **Toda la lógica científica vive en el
paquete de la tesis** (ver `etapas.py`).
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import almacen, etapas, trabajos

RAIZ = Path(__file__).resolve().parents[1]
WEB = RAIZ / "web"

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
    """Estado general: si están los datos base y con qué commit de la tesis corre."""
    try:
        import tesis

        version = tesis.__version__
    except Exception:
        version = None
    return {
        "datos_listos": almacen.TABLA_CRUDA.exists(),
        "commit_tesis": almacen.commit_tesis(),
        "version_tesis": version,
        "nodos": len(almacen.listar(_con)),
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
        paso = max(1, len(sub) // limite)  # submuestreo para no mandar miles de puntos
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

@app.get("/")
def raiz():
    return FileResponse(WEB / "index.html")


@app.get("/taller")
def taller():
    return FileResponse(WEB / "taller.html")


app.mount("/estatico", StaticFiles(directory=WEB), name="estatico")

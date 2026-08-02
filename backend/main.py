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


@app.get("/api/nodo/{clave}/datos")
def get_datos(clave: str, limite: int = 200):
    """Datos para graficar, según la etapa del nodo. Siempre acotados: esto va al navegador."""
    nodo = almacen.obtener(_con, clave)
    if nodo is None:
        raise HTTPException(404, "Nodo inexistente")
    if nodo["estado"] != "listo" or not nodo["tiene_resultado"]:
        raise HTTPException(409, "El nodo todavía no tiene resultado")

    salida = almacen.cargar_resultado(clave)
    etapa = nodo["etapa"]

    if etapa == "datos":
        muestra = salida.head(limite)
        return {
            "tipo": "series",
            "columnas": [c for c in salida.columns if c != "SheetName"],
            "filas": json.loads(muestra.to_json(orient="records")),
            "por_hoja": salida.groupby("SheetName").size().sort_values(ascending=False)
                              .head(15).to_dict(),
        }

    if etapa == "ventaneo":
        meta = salida["meta"]
        return {
            "tipo": "ventanas",
            "por_hoja": meta.groupby("SheetName").size().sort_values(ascending=False)
                            .head(15).to_dict(),
            "ejemplo": salida["ventanas"].values[0].tolist() if len(salida["ventanas"]) else [],
            "senales": list(salida["ventanas"].signal_columns),
        }

    if etapa in ("features", "filtrado"):
        tabla = salida.get("filtradas", salida.get("features"))
        cols = [c for c in tabla.columns if c != "SheetName"]
        return {"tipo": "features", "columnas": cols[:limite], "total": len(cols)}

    if etapa == "deteccion":
        sc = salida["scores"]
        return {
            "tipo": "scores",
            "detectores": list(sc.columns),
            # Histograma por detector, normalizado a percentiles para que sean comparables en pantalla
            "percentiles": {c: [float(sc[c].quantile(q / 100)) for q in range(0, 101, 5)]
                            for c in sc.columns},
        }

    if etapa == "eventos":
        tabla = salida["eventos"]
        return {
            "tipo": "eventos",
            "columnas": list(tabla.columns),
            "filas": json.loads(tabla.head(limite).to_json(orient="records")),
        }

    return {"tipo": "desconocido"}


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
        acum[desde:desde + bloque.shape[0], :] = bloque

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

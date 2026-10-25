"""Exporta lo que respondieron los revisores sobre una rama, para la Etapa 2 del paquete de la tesis.

Por qué existe: la derivación de etiquetas vive en el repositorio de la tesis (`tesis.etiquetas`,
rama `stage2`, ADR-0009), y ese código no lee la base del taller —su esquema es asunto de acá y puede
cambiar—. Lee este archivo, con un formato fijo y versionado: `juicios-taller/1`.

QUÉ VA. Por cada evento que alguien tocó: su hoja, tramo y rango, y por revisor la respuesta, el
comentario y las secciones. El rango va para que del otro lado se verifique que es el mismo evento
y no se confíe en el número: `event_id` solo significa lo mismo con la misma configuración y el
mismo código. Por lo mismo va la configuración de la rama y el commit de la tesis.

QUIÉN DIJO QUÉ VA CON NOMBRE. Es el mismo dato que ve el administrador en el catálogo; quien corre
esto es quien prepara las etiquetas, no un revisor cuya independencia haya que cuidar.

Uso (dentro del contenedor del taller):
    python scripts/exportar_juicios.py [--nodo CLAVE] [--salida archivo.json]

Sin `--nodo`, toma la única rama de eventos con resultado; si hay más de una, las lista y pide elegir.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import ajustes, almacen, clasificacion  # noqa: E402  (necesita el sys.path de arriba)

FORMATO = "juicios-taller/1"


def _nativo(v):
    """numpy → Python, para que `json` no tropiece con un `int64`."""
    return v.item() if hasattr(v, "item") else v


def config_de_la_rama(cadena: list[dict]) -> dict:
    """Los cuatro parámetros que deciden qué es un evento, con los nombres del paquete de la tesis."""
    p = {n["etapa"]: n["parametros"] or {} for n in cadena}
    ventaneo, eventos = p.get("ventaneo", {}), p.get("eventos", {})
    maximo = eventos.get("max_ventanas_evento")
    return {
        "window_size": int(ventaneo["tamano_ventana"]),
        "use_dedup": bool(ventaneo["deduplicar"]),
        "candidate_fraction": float(eventos["fraccion_candidatos"]),
        "max_event_windows": int(maximo) if maximo else None,
    }


def armar(nodo: dict, cadena: list[dict], tabla_eventos, juicios_por_evento: dict) -> dict:
    """El contenido del archivo. Función pura: recibe todo y no toca ninguna base.

    `juicios_por_evento` es lo que devuelve `clasificacion.catalogado()` para esta rama:
    `{event_id: [{usuario, respuesta, comentario, secciones, …}, …]}`.
    """
    por_id = tabla_eventos.set_index("event_id")
    eventos = []
    for eid in sorted(juicios_por_evento):
        if eid not in por_id.index:
            # Un juicio sobre un evento que la rama ya no tiene. No debería pasar —borrar la rama
            # borra sus juicios—, y si pasa se avisa en vez de exportar algo sin rango.
            raise ValueError(f"El evento {eid} tiene juicios pero no está en la tabla de la rama")
        ev = por_id.loc[eid]
        eventos.append({
            "event_id": int(eid),
            "hoja": _nativo(ev["SheetName"]),
            "segmento": _nativo(ev["segment"]),
            "desde": int(ev["start"]),
            "hasta": int(ev["end"]),
            "revisores": [
                {
                    "usuario": r["usuario"],
                    "respuesta": r["respuesta"],
                    "comentario": r["comentario"],
                    "secciones": [
                        {"desde": int(s["desde"]), "hasta": int(s["hasta"]),
                         "respuesta": s["respuesta"], "comentario": s["comentario"]}
                        for s in r.get("secciones", [])
                    ],
                }
                for r in juicios_por_evento[eid]
            ],
        })
    return {
        "formato": FORMATO,
        "exportado_en": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "nodo": nodo["clave"],
        "etiqueta_rama": nodo.get("etiqueta"),
        "commit_tesis": nodo.get("commit_tesis"),
        "config": config_de_la_rama(cadena),
        "eventos": eventos,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--nodo", help="clave del paso de eventos; sin esto, la única que haya")
    ap.add_argument("--salida", type=Path, help="archivo a escribir (por omisión, en la carpeta de datos)")
    args = ap.parse_args()

    con = almacen.conectar()
    clave = args.nodo
    if clave is None:
        candidatos = [n for n in almacen.listar(con)
                      if n["etapa"] == "eventos" and n["tiene_resultado"]]
        if len(candidatos) != 1:
            print("Hay que elegir la rama con --nodo. Pasos de eventos con resultado:")
            for n in candidatos:
                print(f"  {n['clave']}  {n.get('etiqueta') or ''}")
            return 2
        clave = candidatos[0]["clave"]

    nodo = almacen.obtener(con, clave)
    if nodo is None or nodo["etapa"] != "eventos" or not nodo["tiene_resultado"]:
        print(f"{clave}: no es un paso de eventos con resultado")
        return 2

    clasificacion.preparar()
    contenido = armar(
        nodo,
        almacen.cadena_hasta(con, clave),
        almacen.cargar_resultado(clave)["eventos"],
        clasificacion.catalogado().get(clave, {}),
    )
    destino = args.salida or ajustes.DIR_DATOS / f"juicios_{clave}.json"
    destino.write_text(json.dumps(contenido, ensure_ascii=False, indent=2), encoding="utf-8")
    n_rev = sum(len(e["revisores"]) for e in contenido["eventos"])
    print(f"{len(contenido['eventos'])} eventos, {n_rev} juicios → {destino}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Diagnóstico de la instalación: qué configuración se está usando y si falta algo.

Uso:  python scripts/verificar.py   (o `mise run check`)
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> int:
    from backend import ajustes

    print("Configuración del taller")
    print("─" * 62)

    problemas: list[str] = []

    ruta = ajustes.ruta_tesis()
    try:
        import tesis

        origen = "deducida del paquete instalado"
        print(f"  repo de la tesis   {ruta}   ({origen})")
        print(f"  paquete `tesis`    versión {tesis.__version__}")
    except ImportError:
        print(f"  repo de la tesis   {ruta}   (de RUTA_TESIS; el paquete NO está instalado)")
        problemas.append(f"El paquete `tesis` no está instalado. Corré:  mise run install\n"
                         f"     (busca el repo en {ruta}; si tu clon está en otro lado o tiene otro\n"
                         f"      nombre, poné RUTA_TESIS en el archivo .env)")

    if not ruta.exists():
        problemas.append(f"La ruta {ruta} no existe. Ajustá RUTA_TESIS en .env")

    from backend.almacen import commit_tesis

    print(f"  commit             {commit_tesis()}")
    print(f"  datos locales      {ajustes.DIR_DATOS}")
    print(f"  puerto             {ajustes.PUERTO}")

    print()
    print("Estado de los datos")
    print("─" * 62)
    if ajustes.TABLA_CRUDA.exists():
        mb = ajustes.TABLA_CRUDA.stat().st_size / 1e6
        print(f"  tabla cruda        lista ({mb:.2f} MB)")
    else:
        print("  tabla cruda        FALTA")
        problemas.append("Falta la tabla cruda. Generala una vez con:  mise run datos")

    if ajustes.DIR_CACHE.exists():
        archivos = list(ajustes.DIR_CACHE.glob("*.joblib"))
        mb = sum(f.stat().st_size for f in archivos) / 1e6
        print(f"  caché de etapas    {len(archivos)} resultados ({mb:.1f} MB)")
    else:
        print("  caché de etapas    vacío")

    if ajustes.BASE_SQLITE.exists():
        import sqlite3

        con = sqlite3.connect(ajustes.BASE_SQLITE)
        n = con.execute("SELECT count(*) FROM nodos").fetchone()[0]
        print(f"  árbol de ramas     {n} pasos registrados")
    else:
        print("  árbol de ramas     vacío (se crea solo al primer uso)")

    print()
    print("Configuración de referencia de la tesis")
    print("─" * 62)
    origen = ajustes.origen_config()
    print(f"  sale de: {origen['fuente']}")
    if origen.get("problema"):
        print(f"  ATENCIÓN: no se pudo leer del paquete ({origen['problema']}).")
        print("            Los valores de abajo son un respaldo fijo del taller, no los de la tesis.")
        problemas.append("La configuración de referencia no sale de la tesis sino de un respaldo. "
                         "Revisá que el paquete `tesis` esté instalado y actualizado.")
    if origen.get("sobreescritos"):
        print(f"  pisado por el .env: {origen['sobreescritos']}")
    print()
    for etapa, params in ajustes.CONFIG_TESIS.items():
        if params:
            print(f"  {etapa:11s} " + " · ".join(f"{k}={v}" for k, v in params.items()))

    print()
    if problemas:
        print("Falta resolver:")
        for i, p in enumerate(problemas, 1):
            print(f"  {i}. {p}")
        return 1
    print("Todo en orden. Levantalo con:  mise run dev")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Precalcula la tabla cruda: lee el Excel una sola vez y la guarda para que el taller arranque de ahí.

Por qué existe: leer las 42 hojas del Excel tarda ~36 s, el 40 % de una corrida completa, y no tiene
ninguna decisión configurable adentro (salvo qué hojas entran, que se resuelve después filtrando la
tabla). Precalcularlo una vez ahorra esos 36 s en **cada** ejecución de **cada** rama.

IMPORTANTE: se guarda con `joblib` y no como CSV porque `preprocessing.clean` necesita el índice
original del Excel para detectar los tramos contiguos. Si el índice se pierde, los segmentos salen mal
**sin dar error**.

Uso:
    python scripts/exportar_crudo.py [--todas-las-hojas]
"""

from __future__ import annotations

import argparse
import dataclasses
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend import ajustes  # noqa: E402  (necesita el sys.path de arriba)

DESTINO = ajustes.TABLA_CRUDA


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--todas-las-hojas", action="store_true",
        help="Incluye también las hojas excluidas por el ADR (laboratorio y 'Anomalous data'), para "
             "que el taller pueda mostrarlas y permitir activarlas. Puede fallar si alguna tiene otro "
             "formato de columnas.",
    )
    args = ap.parse_args()

    try:
        import joblib
        from tesis import io
        from tesis.config import CONFIG
    except ImportError as e:
        print(f"No se pudo importar el paquete de la tesis: {e}", file=sys.stderr)
        print(f"Instalalo con:  mise run install   (busca el repo en {ajustes.ruta_tesis()})",
              file=sys.stderr)
        print("Si tu clon está en otro lado o tiene otro nombre, poné RUTA_TESIS en el .env",
              file=sys.stderr)
        return 1

    cfg = CONFIG.data
    if args.todas_las_hojas:
        cfg = dataclasses.replace(cfg, excluded_sheets=())

    print(f"Leyendo {cfg.excel_path.name} …", flush=True)
    t = time.time()
    try:
        crudo = io.load_raw_sheets(cfg)
    except Exception as e:
        if args.todas_las_hojas:
            print(f"Falló con todas las hojas ({type(e).__name__}: {e}).", file=sys.stderr)
            print("Reintentá sin --todas-las-hojas.", file=sys.stderr)
            return 1
        raise

    DESTINO.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(crudo, DESTINO, compress=3)

    print(f"  {len(crudo)} filas · {crudo['SheetName'].nunique()} hojas · "
          f"{time.time() - t:.1f} s")
    print(f"  índice preservado: {crudo.index.is_monotonic_increasing}")
    print(f"→ {DESTINO}  ({DESTINO.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

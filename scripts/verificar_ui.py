"""Comprueba que todo `#id` que el JavaScript consulta exista de verdad.

Por qué existe: `$('#algo')` sobre un id inexistente devuelve `null`, y el
`.addEventListener` que sigue tira «Cannot read properties of null». Si eso pasa
durante el arranque, **no falla ese botón: falla la página entera**, porque corta
la función que la inicializa. Es un error que no aparece ni en `node --check` ni
en las respuestas del servidor —el HTML y el JS se sirven perfectos— y sólo se ve
abriendo el navegador.

Pasó de verdad: se agregó el `addEventListener` de un botón y el botón nunca se
insertó en el HTML, así que el taller quedó sin arrancar. Esta comprobación lo
detecta en un segundo.

Uso:  python scripts/verificar_ui.py   (incluido en `mise run check`)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web"


def main() -> int:
    js = {f.name: f.read_text() for f in sorted(WEB.glob("*.js"))}
    if not js:
        print("  (no hay JS que revisar)")
        return 0
    html = "\n".join(f.read_text() for f in sorted(WEB.glob("*.html")))
    todo = "\n".join(js.values())

    usados = set(re.findall(r"""\$\(['"]#([\w-]+)['"]\)""", todo))
    usados |= set(re.findall(r"""getElementById\(['"]([\w-]+)['"]\)""", todo))

    # Existen: los del HTML estático y los que el propio JS escribe en sus plantillas.
    existen = set(re.findall(r'id="([\w-]+)"', html)) | set(re.findall(r'id="([\w-]+)"', todo))

    # Ids armados por interpolación (`id="g-${nombre}"`): no se pueden resolver sin ejecutar,
    # así que se acepta cualquier id que empiece con ese prefijo.
    prefijos = [p for p in re.findall(r'id="([\w-]*)\$\{', todo)]
    dinamico = lambda i: any(p and i.startswith(p) for p in prefijos)

    faltan = sorted(i for i in usados - existen if not dinamico(i))

    print(f"  ids consultados por el JS : {len(usados)}")
    print(f"  prefijos dinámicos        : {', '.join(sorted(set(p for p in prefijos if p))) or '—'}")
    if not faltan:
        print("  sin referencias colgadas ✓")
        return 0

    print(f"  REFERENCIAS COLGADAS      : {len(faltan)}")
    for i in faltan:
        for nombre, src in js.items():
            for n, linea in enumerate(src.splitlines(), 1):
                if re.search(r"""\$\(['"]#%s['"]\)""" % re.escape(i), linea):
                    print(f"    #{i}  ({nombre}:{n})  {linea.strip()[:88]}")
    print("\n  Si el uso está en el arranque, la página entera no carga.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

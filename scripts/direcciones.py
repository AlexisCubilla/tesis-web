"""Imprime en qué direcciones va a quedar disponible el taller antes de levantarlo.

Existe porque el error más fácil de cometer es levantar el servidor escuchando solo en 127.0.0.1 y
después no entender por qué no se ve desde el celular o desde otra computadora. Mostrar las
direcciones al arrancar convierte eso en algo evidente.
"""

from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def ip_de_la_red() -> str | None:
    """IP de esta máquina en la red local. No abre ninguna conexión real."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.0.2.1", 1))  # dirección de documentación (RFC 5737), no existe
        return s.getsockname()[0]
    except OSError:
        return None
    finally:
        s.close()


def main() -> int:
    from backend import ajustes

    host = os.environ.get("HOST", "0.0.0.0").strip() or "0.0.0.0"
    puerto = os.environ.get("PUERTO", "").strip() or str(ajustes.PUERTO)

    print()
    if host in ("0.0.0.0", "::"):
        print("  El taller va a estar disponible en:")
        print(f"    · en esta máquina        http://localhost:{puerto}")
        ip = ip_de_la_red()
        if ip:
            print(f"    · desde la misma red     http://{ip}:{puerto}")
            print("      (otra computadora, el celular, para mostrarlo en una reunión)")
        else:
            print("    · desde la red: no se pudo detectar la IP; miralo con  ip addr")
    else:
        print(f"  El taller va a estar disponible SOLO en  http://{host}:{puerto}")
        print("  Para verlo desde otro dispositivo de la red, poné  HOST=0.0.0.0  en el .env")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

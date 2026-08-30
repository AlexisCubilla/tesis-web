# Imagen del taller. Incluye el paquete de la tesis instalado desde el repo hermano montado.
#
# El repo de la tesis NO se copia dentro de la imagen: se monta como volumen (ver podman-compose.yml).
# Así la imagen no queda atada a una versión del pipeline y siempre se ve, en pantalla, con qué commit
# se está ejecutando.

FROM docker.io/library/python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# hdbscan y pyclustering compilan extensiones nativas; git para leer el commit de la tesis.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Las dependencias científicas se instalan desde el requirements del repo de la tesis, que se monta
# en /tesis. Se hace en el arranque porque el repo es un volumen, no parte de la imagen.
#
# Pero compilarlas cada vez cuesta minutos (hdbscan y pyclustering traen extensiones nativas), y el
# arranque las recompilaba en cada contenedor nuevo. Esta copia del requirements de la tesis las deja
# prehorneadas en la imagen: al arrancar, pip las encuentra satisfechas y no hace nada.
#
# NO es una fuente de verdad, es una semilla de caché. El CMD sigue corriendo `pip install -e /tesis`,
# que resuelve las dependencias contra el requirements.txt REAL del repo montado y reconcilia lo que
# haga falta. Si esta copia queda desactualizada, el arranque es más lento; nunca incorrecto.
#
# Para volver a sincronizarla:  cp $RUTA_TESIS/requirements.txt requirements-tesis.txt
COPY requirements-tesis.txt ./
RUN pip install -r requirements-tesis.txt

COPY backend/ ./backend/
COPY web/ ./web/
COPY scripts/ ./scripts/

EXPOSE 8000

# `pip install -e /tesis` en el arranque: instala el paquete montado y levanta el servidor.
CMD ["sh", "-c", "pip install -e /tesis && exec uvicorn backend.main:app --host 0.0.0.0 --port 8000"]

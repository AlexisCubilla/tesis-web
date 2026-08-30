"""Sirve el Document Server a través del propio taller, en el mismo origen.

Por qué existe
--------------
El editor se cargaba desde `http://localhost:8080` dentro de una página servida por
`http://localhost:8000`. Para el navegador eso es un marco **de otro origen**, y ahí cada navegador
decide por su cuenta cuánto le presta: Firefox, con su protección de rastreo, le parte o le niega el
almacenamiento a los marcos de terceros. El editor de OnlyOffice lee almacenamiento mientras arranca,
así que se moría antes de emitir su primer evento — sin error, sin nada: la pantalla se quedaba
cargando para siempre. En Chromium el mismo montaje andaba, que es lo que hizo tan difícil verlo.

Sirviendo todo desde un solo origen el problema no se arregla: **deja de existir**. No hay marco de
tercero que particionar. De paso, el puerto 8080 no necesita estar publicado, y el día que haya TLS
hay un solo lugar donde ponerlo.

Cómo funciona
-------------
No se reescribe ni una ruta. Las del taller y las del Document Server no se pisan:

    taller               /  ·  /taller  ·  /revision  ·  /api/*  ·  /estatico/*
    Document Server      /web-apps/*  ·  /sdkjs/*  ·  /doc/*  ·  /coauthoring/*  ·  …

así que alcanza con reenviar los prefijos de la lista de abajo tal cual, al mismo path. Eso evita el
problema clásico de meter OnlyOffice bajo un subdirectorio, donde hay que reescribir las URLs que él
mismo genera y siempre se escapa alguna.

El editor además cuelga todo de un prefijo con su huella de compilación (`/9.4.0-<hash>/…`), que
cambia en cada arranque del servidor. Por eso hay un comodín que lo reconoce por forma.
"""

from __future__ import annotations

import re

import httpx
import websockets
from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import Response, StreamingResponse

from . import ajustes

router = APIRouter()

#: Prefijos que le pertenecen al Document Server. Salen de su propia configuración de nginx
#: (`/etc/nginx/includes/ds-docservice.conf`).
PREFIJOS = (
    "web-apps", "sdkjs", "sdkjs-plugins", "fonts", "dictionaries", "cache",
    "coauthoring", "internal", "info", "meta", "downloadas", "doc",
)

#: Archivos y puntos de entrada sueltos que viven en la raíz del Document Server.
ARCHIVOS = (
    "themes.json", "document_editor_service_worker.js", "healthcheck",
    "ConvertService.ashx", "FileUploader.ashx",
)

#: `9.4.0-f038d87f…`: el prefijo con la huella de compilación. Cambia en cada arranque del servidor,
#: así que se lo reconoce por forma y no por valor.
VERSION = re.compile(r"^\d+\.\d+\.\d+[-.][0-9a-zA-Z]+$")

#: Encabezados que NO se le reenvían al Document Server al abrir el websocket: son del apretón de
#: manos y los pone la biblioteca. Mandarlos también nosotros los duplica y nginx contesta 400.
#: Todo lo demás sí va —sobre todo la cookie de sesión de socket.io—.
SALTEAR_WS = {
    "host", "connection", "upgrade", "sec-websocket-key", "sec-websocket-version",
    "sec-websocket-extensions", "sec-websocket-protocol", "sec-websocket-accept",
    "content-length", "keep-alive", "transfer-encoding",
}

#: Encabezados que no se reenvían: son de la conexión, no del mensaje, y arrastrarlos rompe la
#: respuesta (sobre todo `content-length` cuando el cuerpo va en trozos).
#:
#: `content-encoding` NO está en la lista, y es a propósito. El cuerpo se copia tal cual viene
#: (`aiter_raw`), o sea todavía comprimido; si no se reenviara el encabezado que lo dice, pasarían
#: dos cosas malas a la vez: el navegador recibiría gzip creyendo que es texto plano, y el
#: `GZipMiddleware` del taller lo comprimiría **por segunda vez**. El resultado es un `api.js` que
#: baja con 200, pesa lo que tiene que pesar y no define nada — el editor no arranca y no hay ningún
#: error que lo explique.
#:
#: Reenviándolo, el middleware ve que la respuesta ya viene codificada y no la toca.
SALTEAR = {
    "host", "connection", "keep-alive", "transfer-encoding", "upgrade",
    "proxy-authenticate", "proxy-authorization", "te", "trailer", "content-length",
}

#: El editor pide `common/Analytics.js`, y **los bloqueadores de publicidad lo filtran por el
#: nombre**: no miran qué hace, miran cómo se llama. Es un envoltorio de Google Analytics de 3,7 KB
#: que sin `_gaq` no hace absolutamente nada, pero `app.js` lo declara como dependencia de requirejs,
#: así que cuando el pedido se aborta hay riesgo de que el editor no termine de arrancar — y lo hace
#: en silencio, sin error que lo explique.
#:
#: Se lo sirve con otro nombre, y se reescribe la referencia en el bundle que lo pide. El archivo es
#: el mismo; lo único que cambia es que ya no se parece a algo que haya que bloquear.
NOMBRE_REAL = "web-apps/apps/common/Analytics.js"
NOMBRE_NEUTRO = "web-apps/apps/common/Medicion.js"

#: Los bundles donde hay que reescribir la referencia.
_APP_JS = re.compile(r"^(?:\d+\.\d+\.\d+[-.][0-9a-zA-Z]+/)?web-apps/apps/[^/]+/(?:main|forms)/app\.js$")

_cliente: httpx.AsyncClient | None = None


def cliente() -> httpx.AsyncClient:
    """Un cliente compartido: reusar conexiones importa cuando el editor pide cientos de archivos."""
    global _cliente
    if _cliente is None:
        _cliente = httpx.AsyncClient(
            base_url=ajustes.OO_URL_INTERNA or "http://onlyoffice",
            timeout=httpx.Timeout(60.0, connect=10.0),
            follow_redirects=False,
        )
    return _cliente


async def cerrar() -> None:
    global _cliente
    if _cliente is not None:
        await _cliente.aclose()
        _cliente = None


def le_toca_al_document_server(ruta: str) -> bool:
    """¿Esta ruta es del Document Server?

    Se decide sobre el PRIMER tramo: o es uno de sus prefijos, o es un archivo suelto conocido, o es
    el prefijo con la huella de compilación (y entonces lo que sigue es cosa suya).
    """
    primero = ruta.lstrip("/").split("/", 1)[0]
    return primero in PREFIJOS or primero in ARCHIVOS or bool(VERSION.match(primero))


@router.api_route(
    "/{ruta:path}",
    methods=["GET", "POST", "PUT", "DELETE", "HEAD", "OPTIONS", "PATCH"],
    include_in_schema=False,
)
async def reenviar(ruta: str, request: Request):
    """Reenvía al Document Server, en streaming.

    En streaming y no de un saque porque algunos de sus archivos son grandes (el diccionario, las
    fuentes) y no tiene sentido juntarlos enteros en memoria para volver a soltarlos.
    """
    if not le_toca_al_document_server(ruta):
        return Response(status_code=404)

    # El alias: lo que se pide con el nombre neutro se trae del archivo real.
    if ruta.endswith(NOMBRE_NEUTRO):
        ruta = ruta[: -len(NOMBRE_NEUTRO)] + NOMBRE_REAL

    if _APP_JS.match(ruta):
        return await _reenviar_reescribiendo(ruta, request)

    cabeceras = {k: v for k, v in request.headers.items() if k.lower() not in SALTEAR}

    # El `Host` del taller viaja como `X-Forwarded-Host`, NO como `Host`.
    #
    # Hace falta que llegue de alguna forma porque el Document Server arma con él las URLs que
    # después le da al navegador —entre ellas la del documento convertido, en `/cache/…`—; si usara
    # el nombre con el que lo ve el taller por dentro, el editor recibiría una URL que no puede
    # resolver y fallaría con «Error de descarga» (-4).
    #
    # Pero mandarlo como `Host` rompe otra cosa, y peor: cuando el Document Server está detrás de un
    # nginx compartido, el `Host` es lo que decide a qué sitio entra la petición. Pidiéndole a
    # `docs.…` un archivo con `Host: demo.…`, la petición aterriza en el sitio del taller, que no
    # tiene `/web-apps/` y contesta 404 — un 404 que el proxy reenvía tal cual y parece suyo.
    #
    # Así que el `Host` lo pone httpx a partir de OO_URL_INTERNA (el destino real) y el nombre de
    # cara al navegador va en `X-Forwarded-Host`, que es para lo que existe.
    if (host := request.headers.get("host")):
        cabeceras.pop("host", None)
        cabeceras.setdefault("x-forwarded-host", host)
    cabeceras.setdefault("x-forwarded-proto", request.url.scheme)

    pedido = cliente().build_request(
        request.method,
        "/" + ruta,
        params=dict(request.query_params),
        headers=cabeceras,
        content=request.stream(),
    )
    respuesta = await cliente().send(pedido, stream=True)

    salida = {k: v for k, v in respuesta.headers.items() if k.lower() not in SALTEAR}
    return StreamingResponse(
        respuesta.aiter_raw(),
        status_code=respuesta.status_code,
        headers=salida,
        background=_cerrar_luego(respuesta),
    )


async def _reenviar_reescribiendo(ruta: str, request: Request) -> Response:
    """Trae el bundle del editor y le cambia la referencia a Analytics por la del nombre neutro.

    Este es el único caso en que el proxy mira el contenido en vez de copiarlo tal cual, así que va
    aparte y bien acotado: solo los `app.js` de los editores, y solo una sustitución.

    Acá no se puede ir en trozos —hay que tener el texto entero para sustituir— pero es un archivo
    por editor y queda cacheado en el navegador, así que se paga una vez.
    """
    cabeceras = {k: v for k, v in request.headers.items() if k.lower() not in SALTEAR}
    # Mismo criterio que en `reenviar`: el `Host` lo pone httpx desde OO_URL_INTERNA, y el del
    # taller viaja como `X-Forwarded-Host`. Mandarlo como `Host` haría aterrizar la petición en otro
    # sitio del mismo nginx.
    if (host := request.headers.get("host")):
        cabeceras.pop("host", None)
        cabeceras.setdefault("x-forwarded-host", host)
    # Se pide sin comprimir para poder sustituir sobre el texto sin descomprimir a mano.
    cabeceras["accept-encoding"] = "identity"

    r = await cliente().get("/" + ruta, headers=cabeceras, params=dict(request.query_params))
    if r.status_code != 200:
        return Response(content=r.content, status_code=r.status_code,
                        headers={k: v for k, v in r.headers.items() if k.lower() not in SALTEAR})

    cuerpo = r.text.replace("common/Analytics", "common/Medicion")
    salida = {k: v for k, v in r.headers.items() if k.lower() not in SALTEAR}
    # El middleware del taller se encarga de comprimirlo al salir.
    return Response(content=cuerpo, status_code=200, headers=salida,
                    media_type=r.headers.get("content-type", "application/javascript"))


def _cerrar_luego(respuesta: httpx.Response):
    from starlette.background import BackgroundTask

    return BackgroundTask(respuesta.aclose)


@router.websocket("/{version}/doc/{ruta:path}")
async def reenviar_websocket_versionado(ws: WebSocket, version: str, ruta: str):
    """El mismo relé, para cuando el editor cuelga el websocket de su prefijo de compilación.

    Y es lo que hace **siempre**: pide `/9.4.0-<hash>/doc/<clave>/c/`, no `/doc/<clave>/c/`. Sin esta
    ruta el pedido cae en el reenvío HTTP, que no puede hacer el cambio a websocket; socket.io no se
    queja, se cae calladito a *long-polling* y el documento nunca termina de llegar. En el registro
    del taller se ve clarísimo una vez que se sabe qué mirar: `transport=polling` contestando 200 una
    y otra vez, sin que pase nada.
    """
    if not VERSION.match(version):
        await ws.close(code=1008)
        return
    await _relevar(ws, f"/{version}/doc/{ruta}")


@router.websocket("/doc/{ruta:path}")
async def reenviar_websocket(ws: WebSocket, ruta: str):
    """Relé del websocket del editor, que es por donde pide y recibe el documento."""
    await _relevar(ws, f"/doc/{ruta}")


async def _relevar(ws: WebSocket, camino: str):
    """Copia el websocket en los dos sentidos hasta que alguna de las dos puntas corta.

    Sin esto el editor carga su interfaz y se queda esperando: el documento viaja por acá, no por
    HTTP.
    """
    import asyncio

    base = (ajustes.OO_URL_INTERNA or "http://onlyoffice").replace("http", "ws", 1)
    consulta = str(ws.url.query)
    destino = f"{base}{camino}" + (f"?{consulta}" if consulta else "")

    # El `Host` original también acá, por el mismo motivo que en el reenvío HTTP y con una
    # consecuencia todavía más difícil de rastrear: la sesión de edición se abre por este websocket,
    # y con ella el Document Server arma la URL del documento que le va a pasar al navegador. Sin
    # este encabezado la arma contra `onlyoffice` —el nombre que solo existe dentro de la red de
    # compose— y el navegador no la puede resolver.
    #
    # El editor entonces avisa «Error de descarga» (código -4), que hace pensar en el servidor
    # cuando el que no pudo bajar nada fue el navegador. Y del lado del servidor no queda ni una
    # línea de registro, porque para él salió todo bien: bajó el archivo y mandó sus callbacks.
    # OJO: acá NO va `Host`. La biblioteca de websockets pone el suyo a partir de la URI, así que
    # agregarlo a mano manda el encabezado DOS veces y nginx contesta 400. Y el 400 no se nota:
    # socket.io no protesta, se cae a *long-polling*, cada encuesta se cuelga 25 segundos y lo único
    # que se ve es que el editor tarda una eternidad en abrir.
    #
    # No hace falta: el apretón de manos de socket.io arranca por HTTP —que sí pasa por el reenvío de
    # arriba, con el `Host` correcto—, así que el Document Server ya sabe con qué nombre lo ven.
    # Se le pasan al Document Server los encabezados del navegador, menos los del apretón de manos
    # —esos los pone la biblioteca, y duplicarlos hace que nginx conteste 400—.
    #
    # Lo importante que va acá es la **cookie**. socket.io arranca por HTTP (long-polling), y ese
    # tramo pasa por el reenvío de arriba, así que el navegador recibe la cookie de sesión. Cuando
    # después sube a websocket la manda de vuelta — y si el relé la tira, el Document Server recibe
    # una conexión que no puede atar a ninguna sesión y contesta «Bad request» (engine.io código 3).
    #
    # Desde afuera eso se ve como que el editor abre y el documento no llega nunca: socket.io se cae
    # a long-polling, la sesión se pierde y el editor termina reportando «Error de descarga» — que
    # apunta al archivo cuando el archivo nunca tuvo nada de malo.
    cabeceras = {k: v for k, v in ws.headers.items() if k.lower() not in SALTEAR_WS}
    if (host := ws.headers.get("host")):
        cabeceras["X-Forwarded-Host"] = host
    cabeceras["X-Forwarded-Proto"] = "https" if ws.url.scheme == "wss" else "http"

    await ws.accept()
    try:
        async with websockets.connect(
            destino, open_timeout=20, ping_interval=None, additional_headers=cabeceras
        ) as arriba:

            async def hacia_arriba():
                while True:
                    msg = await ws.receive()
                    if msg["type"] == "websocket.disconnect":
                        break
                    if (t := msg.get("text")) is not None:
                        await arriba.send(t)
                    elif (b := msg.get("bytes")) is not None:
                        await arriba.send(b)

            async def hacia_abajo():
                async for msg in arriba:
                    if isinstance(msg, bytes):
                        await ws.send_bytes(msg)
                    else:
                        await ws.send_text(msg)

            tareas = [asyncio.create_task(hacia_arriba()), asyncio.create_task(hacia_abajo())]
            _, pendientes = await asyncio.wait(tareas, return_when=asyncio.FIRST_COMPLETED)
            for t in pendientes:
                t.cancel()
    except WebSocketDisconnect:
        pass
    except Exception as e:
        # Que se caiga el relé no puede tumbar al taller, pero SÍ tiene que dejar rastro: si esto
        # falla, socket.io no protesta — se cae a *long-polling*, cada encuesta se cuelga sus buenos
        # 25 segundos y el editor tarda una eternidad en abrir. Sin este registro parece lentitud
        # inexplicable en vez de un relé roto.
        import logging

        logging.getLogger("uvicorn.error").warning(
            "rele del websocket caido (%s: %s) — el editor se va a caer a long-polling y va a ir "
            "lentísimo. destino=%s", type(e).__name__, e, destino,
        )
    finally:
        try:
            await ws.close()
        except Exception:
            pass

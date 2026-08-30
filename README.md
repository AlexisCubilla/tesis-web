# Taller — Etapa 1

Sitio didáctico y banco de experimentación de la Etapa 1 de la tesis *"Detección y clasificación de
anomalías en el consumo de baterías satelitales mediante un enfoque híbrido no supervisado-supervisado"*
(UNA–FPUNA; Cubilla, Recalde).

Dos cosas en una:

- **Una página que explica el proyecto** paso a paso, con gráficos y animaciones, para quien no conoce
  el trabajo.
- **Un taller** donde se puede cambiar cualquier parámetro del pipeline, ejecutarlo de verdad y
  comparar caminos. Cada cambio abre una **rama** que queda guardada.

> **El registro canónico de la tesis NO vive acá.** El código del pipeline, las decisiones (ADR) y los
> resultados oficiales están en el repositorio de la tesis. Este repo lo *usa* y lo *explica*; las
> ramas del taller son exploración, no resultados firmados.

## Este repo NO funciona solo

El taller **no contiene el pipeline ni los datos**: los importa. Para levantarlo hace falta tener
también el repositorio de la tesis, que es privado (pedíselo a los autores) y contiene:

- `src/tesis/` — el pipeline, que este taller instala como dependencia y ejecuta
- `data/raw/*.xlsx` — la telemetría del satélite, que nunca se copia acá
- `docs/decisions/` — los ADR, que son la justificación de cada parámetro

Dónde lo tenés clonado se indica con `RUTA_TESIS` en el `.env`; el nombre de la carpeta no importa.

## Cómo funciona

El backend **no reimplementa nada**: instala el paquete `tesis` y llama a sus funciones. Si la web
recalculara features o consolidara eventos por su cuenta, con el tiempo mostraría números distintos a
los de la tesis.

```
repo de la tesis  (privado)        tesis-web  (este, público)
  src/tesis/        ──importa──→     backend/etapas.py   envuelve cada etapa
  data/raw/*.xlsx   ──lee 1 vez──→   data/crudo.joblib   tabla cruda, local, no versionada
  config.py         ──lee──────→     configuración de referencia (★)
```

> **Qué se publica y qué no.** Este repositorio contiene solo código y documentación. La telemetría del
> satélite, los resultados de las corridas y los PDF de la bibliografía **no están acá** y están
> excluidos por `.gitignore`.

### Las ramas salen del caché, no de una estructura

Cada nodo se identifica por un **hash de (etapa + parámetros + nodo padre)**. Dos configuraciones que
comparten el tramo inicial generan las mismas claves en ese tramo, así que **reutilizan lo ya
calculado**. Ramificar es pedir una etapa con otros parámetros sobre el mismo padre; no hay que
programar nada más.

En la práctica:

| Qué cambiás | Qué se recalcula | Cuánto tarda |
|---|---|---|
| Fracción de candidatos, límite de evento | solo la última etapa | ~0,3 s |
| Detectores o sus hiperparámetros | detección + eventos | ~18 s |
| Tamaño de ventana, paso, dedup | todo desde el ventaneo | ~7-30 s |
| Limpieza o selección de hojas | toda la cadena | ~30 s |

## Configuración

Todo lo que depende de la máquina vive en un `.env`. Copiá el ejemplo y ajustá lo que necesites:

```bash
cp .env.example .env
```

La variable que casi seguro vas a querer tocar es **`RUTA_TESIS`**, porque cada uno puede tener el
repositorio de la tesis clonado con otro nombre o en otro lado:

```ini
RUTA_TESIS=../repo-rebuild      # o ../mi-clon-de-la-tesis, /home/…/tesis, lo que sea
```

Una vez que el paquete `tesis` está instalado, el backend **deduce la ruta del propio paquete**, así
que el nombre de la carpeta deja de importar. `RUTA_TESIS` es para instalarlo y para montarlo en el
contenedor.

`.env.example` documenta todas las variables: dónde guardar el estado local (`DIR_DATOS`), el puerto,
en qué direcciones escuchar (`HOST`).

### La configuración de referencia sale de la tesis

Los valores con los que el trabajo reporta sus resultados —ventana 50, dedup 0,95, tope 15, 1 % de
candidatos— **no están escritos en ningún lado de este repo**. Se leen de `src/tesis/config.py`, que
según las reglas de ese repositorio es la fuente única de verdad de todos los parámetros.

Eso alcanza para tres cosas a la vez, siempre sincronizadas:

- el botón **★ Ejecutar tesis**,
- la marca **★** de las ramas que coinciden,
- y **los valores iniciales de los formularios**.

Si en la tesis se firma un cambio por ADR, el taller lo toma solo. Las variables `TESIS_*` del `.env`
están comentadas por defecto y solo sirven para mostrar como referencia algo distinto de lo que dice la
tesis — por ejemplo, una configuración que todavía se está discutiendo.

Para ver qué configuración está tomando y si falta algo:

```bash
mise run check
```

## Instalación (sin contenedor)

Requiere [mise](https://mise.jdx.dev).

```bash
cp .env.example .env  # y ajustá RUTA_TESIS si hace falta
mise install          # Python 3.11
mise run venv         # crea .venv
mise run install      # deps + el paquete `tesis` desde $RUTA_TESIS
mise run datos        # lee el Excel una vez y precalcula la tabla cruda (~40 s)
mise run check        # verifica que esté todo en su lugar
mise run dev          # levanta el taller y muestra en qué direcciones responde
```

Al arrancar imprime dónde quedó disponible:

```
  El taller va a estar disponible en:
    · en esta máquina        http://localhost:8000
    · desde la misma red     http://192.168.0.5:8000
```

Por defecto escucha en todas las direcciones (`HOST=0.0.0.0`), así que se puede abrir desde el celular
o desde otra computadora de la misma red — útil para mostrarlo. Si preferís que solo se vea desde tu
máquina, poné `HOST=127.0.0.1` en el `.env`.

> Si no responde desde otro dispositivo aun con `HOST=0.0.0.0`, suele ser el cortafuegos del sistema
> bloqueando el puerto.

## Con Podman

```bash
cp .env.example .env  # y ajustá RUTA_TESIS si hace falta
podman compose up
```

Levanta el taller y un Document Server de OnlyOffice para la revisión experta. **No hay base de datos
que levantar**: el árbol de ejecuciones es un archivo SQLite y los resultados van a disco. Todo el
estado es la carpeta de datos.

El Document Server es opcional y pesa varios GB. Si no se lo quiere, alcanza con levantar el taller
solo (`podman compose up taller`) y dejar `OO_URL_PUBLICA` vacía en el `.env`: no aparece el botón de
comentar y todo lo demás funciona igual. Ver «La revisión del experto» más abajo.

El repo de la tesis se monta en `/tesis` (escribible solo para que `pip install -e` genere
`src/tesis.egg-info`, que está en `.gitignore` de la tesis), así que la imagen no queda atada a una
versión del pipeline: en la interfaz siempre se muestra con qué commit se está ejecutando.

La primera vez hay que generar la tabla cruda dentro del contenedor:

```bash
podman compose exec taller python scripts/exportar_crudo.py
```

Con `exec` y no con `run`: `run` levanta un contenedor nuevo reemplazando su comando, así que se
saltea el `pip install -e /tesis` del arranque y el script no encuentra el paquete de la tesis.

## Estructura

```
backend/
  etapas.py      definición de las 6 etapas y sus envoltorios sobre `tesis`
  almacen.py     SQLite (árbol) + caché en disco + hash de configuración
  revision.py    los documentos que comenta el experto, con su historial de versiones
  trabajos.py    ejecución en segundo plano (una corrida tarda decenas de segundos)
  main.py        API y servidor de la web
web/
  index.html     página didáctica del proyecto
  taller.html    el banco de trabajo
  revision.html  el editor donde el experto comenta un entregable
  analisis.html  la pantalla de análisis de una rama
  app.js         formularios, árbol de ramas y qué se muestra en cada etapa
  analisis.js    los cuatro cortes de la pantalla de análisis
  grafico.js     el motor de gráficos, único que conoce la librería
  estilos.css    la paleta entera, en variables: un solo bloque, tema oscuro
  vendor/        ECharts, versionado acá adentro (ver web/vendor/LEEME.md)
scripts/
  exportar_crudo.py   precalcula la tabla cruda desde el Excel de la tesis
tests/
  test_reproduccion.py  afirma los números de la tabla de verificación
data/                 estado local (ignorado por git): tabla cruda, caché, SQLite
data/revision/        los documentos del experto y sus versiones — lo único que no se recalcula
docs/arquitectura.md  las decisiones de diseño y por qué
```

## Verificación

El taller reproduce los resultados oficiales de la tesis. Con los valores por defecto:

| | Tesis (corrida oficial) | Taller |
|---|---|---|
| Filas tras limpieza | 24.138 | 24.138 |
| Ventanas tras dedup | 6.102 | 6.102 |
| Características finales | 45 | 45 |
| Eventos candidatos | 40 | 40 |
| Eventos al límite de 15 | 3 | 3 |

Y apagando la limpieza reproduce el camino del borrador previo documentado en el hallazgo H1 de la
tesis: 22.966 ventanas, 6.923 tras dedup, 45 características.

Esa tabla **no se comprueba mirándola**: hay un test que corre la cadena entera y afirma cada número.

```bash
mise run test
```

Vale la pena entender contra qué protege. El taller *importa* el paquete `tesis` de un repositorio
que evoluciona por su cuenta — ese es el diseño, y por eso la interfaz muestra siempre con qué commit
está corriendo. Un ajuste allá que mueva cualquiera de estos números no daría error: daría **otro
número, en silencio**. El test lo convierte en un fallo ruidoso.

## Cómo se navega el taller

**El mapa de ramas** es un dibujo del árbol real de ejecuciones. Las columnas son los 6 pasos del
pipeline y cada círculo es un paso ya corrido; las líneas conectan cada paso con el que lo produjo.
**Una rama se ve como una bifurcación**: donde el camino se abre en dos, ahí se probó otra
configuración.

```
                                                          ┌──○ 1 % · tope 15
  ○ limpio ──○ 50/1 ──○ feat ──○ filtr ──○ 5 métodos ──────┼──○ 5 % · tope 15
      │                                                   └──○ 1 % · sin tope
      └─────○ 100/5 ─○ feat ──○ filtr ──○ 5 métodos ─────────○ 1 % · tope 15
  ○ sin limpiar ─○ 50/1 ─ …
```

**La vista de fase** es el centro de la pantalla. Al hacer clic en un círculo se abre el paso completo:
qué entró y qué salió (`24.138 mediciones → 6.102 tramos`), con qué parámetros, los números clave y la
visualización de sus datos. Cada etapa muestra lo suyo:

| Paso | Qué se ve |
|---|---|
| Datos | la telemetría de una hoja, señal por señal, y cuántas mediciones tiene cada hoja |
| Ventaneo | cuatro tramos de ejemplo dibujados, y cuántos tramos salieron de cada hoja |
| Características | el catálogo de las 72, y cómo se reparte cada una en desvíos estándar |
| Filtrado | cuánto se mueve cada característica con el corte real marcado, y el mapa de correlación que explica cuáles repiten a otra |
| Detección | la distribución de puntajes de cada método, en su propio panel |
| Eventos | dónde cae cada evento a lo largo del registro de su hoja, y la tabla del entregable (al hacer clic en una fila, sus tres señales) |

**Las dos formas de avanzar** están dichas con todas las letras, sin nada implícito:

| Botón | Qué hace |
|---|---|
| `Paso N: … →` | Continúa esta rama con el paso siguiente |
| `Repetir este paso con otros valores` | Vuelve a ejecutar **este mismo** paso partiendo de su padre: si cambiás algo, se abre una rama |

El círculo punteado en el mapa muestra dónde caería el próximo paso antes de ejecutarlo.

**★ Ejecutar tesis** ejecuta las 6 etapas con la configuración con la que el trabajo reporta sus
resultados, para tener siempre una referencia contra la cual comparar. Las ramas que coinciden con esa
configuración quedan marcadas con ★.

**Borrar** elimina el paso seleccionado, todo lo que cuelga de él y sus resultados en disco.

**Llevarse el entregable.** Desde el último paso se descargan los mismos tres Excel que produce el
pipeline de la tesis —el de revisión experta, el presentable y el de contraste normal— pero con la
configuración de *esa* rama. No los reimplementa nadie: son las mismas funciones de `tesis.export`.

Cada archivo abre con una hoja **Procedencia** que dice si la rama coincide con la configuración de
la tesis, con qué commit del paquete se generó y cuál fue su configuración completa. El nombre lo
lleva también: `candidatos_etapa1_tesis.xlsx` contra `candidatos_etapa1_rama-58ef8255.xlsx`. Sin eso,
en unos meses nadie podría decir si el Excel que tiene en la mano salió de la configuración firmada
o de una prueba.

## El análisis de una rama

En los pasos de detección y de eventos, la vista de fase gana una segunda pestaña: **«Análisis de la
rama»**. Muestra cuatro cortes que el paso por sí solo no da:

- **En qué coinciden los métodos.** Cuántos tramos marcan de a pares y cuántos junta cada nivel de
  acuerdo. Es el argumento central del trabajo, que en la tabla de eventos vive comprimido en un «4/5».
- **Cómo reparte los puntajes cada método**, un panel por método porque no son comparables entre sí,
  con el corte de candidatos marcado.
- **Si los candidatos están realmente aislados**, proyectando los tramos a dos dimensiones. Esa
  proyección es solo para mirar: no alimenta ninguna etapa.
- **Qué hace distinta a una candidata**: cuánto se corre cada característica respecto del resto de
  los tramos, en desvíos estándar. Es lo que va a mirar quien tenga que etiquetar en la Etapa 2.
- **Por qué se descartaron esas características**, con el mapa de correlación.

En los nodos de **eventos** aparece además **«¿Es acuerdo, o es duración?»**, que es el único gráfico
del taller que puede contradecir a la tesis. El aviso de la tabla ya decía que «un evento largo tiene
más chances de juntar métodos distintos»; el gráfico muestra que la mediana pasa de 2 tramos con tres
métodos de acuerdo a 12 con cuatro. Plantear la duda y no mostrar la evidencia era lo peor de los dos
mundos.

Está adentro del taller a propósito: la rama es la que tocaste en el mapa, así que no hay que
elegirla ni reconocerla en ningún lado.

## La revisión del experto

La Etapa 2 es «el experto revisa y etiqueta». Esto es por dónde entra ese trabajo.

Desde el último paso, además de descargar los Excel, se abre **Revisión del experto**: los **tres
entregables** de esa rama, editables dentro del navegador. El experto escribe donde quiera —
columnas nuevas, hojas nuevas, comentarios de celda, colores— y cada vez que guarda queda una
versión más. No hay formulario ni lista de etiquetas cerrada, a propósito: la taxonomía de la
Etapa 2 es lo que él tiene que producir, y ofrecerle opciones sería adelantarle la respuesta.

Cada entregable tiene su propio documento y su propio historial, y se pasa de uno a otro con las
solapas de arriba. El que ya tiene comentarios se marca con ✎, para saber de un vistazo dónde hubo
trabajo al volver después de unos días.

> El presentable son 44 hojas con 80 gráficos, y guardar lo reescribe entero con el motor de
> OnlyOffice. Se comprobó que vuelve igual —mismas hojas, mismos gráficos— así que se puede comentar
> sin miedo a perder el formato.

**Por qué no alcanzaba con mandar el Excel por correo.** Apenas el archivo sale del servidor hay
dos copias, y la del experto es la buena mientras la nuestra envejece sin que se note. Acá hay una
sola: vive donde vive el taller, y quien quiera verla entra y la ve.

### Lo que no se puede perder

De todo lo que guarda el taller, esto es lo único que **no se recalcula**. Las ramas, los números y
los gráficos salen del pipeline; si se borran, se vuelven a correr. El juicio de una persona sobre
telemetría que nadie etiquetó, no. De ahí tres decisiones que valen la pena conocer:

| | Qué pasa |
|---|---|
| **Cada guardado deja una versión** | Ninguna pisa a la anterior. Un borrado accidental o una sesión caída se arreglan bajando la versión de antes. La v0 es lo que salió del pipeline, antes de que nadie lo tocara. |
| **El documento no se regenera encima** | Volver a entrar a comentar abre el que ya existe. Volver a correr la rama no lo toca. |
| **Borrar una rama comentada avisa** | El borrado en cascada se planta y dice qué documentos dependen de eso. Si se confirma igual, los pasos se van pero **el documento se queda**: se marca como huérfano y se sigue pudiendo bajar. |

Por lo mismo, la revisión tiene su **propia base** (`data/revision/revision.sqlite`) y no vive en
`ejecuciones.sqlite`. `mise run limpiar` borra el árbol entero para empezar de cero — está bien,
porque se recalcula — y se habría llevado puesto el trabajo del experto de paso.

Respaldar es copiar `data/revision/`. Ahí están los archivos, todas sus versiones y el registro.

### El resumen es un índice, no la verdad

En la pantalla de revisión, al costado, aparece lo que el experto escribió: los comentarios de
celda y lo que puso en columnas que no venían en el entregable. Sirve para buscar sin abrir cuarenta
planillas, y para que la Etapa 3 tenga algo que leer.

**El archivo es el que manda.** Ese resumen se extrae de él y se puede volver a extraer: si la
extracción mejora, se pasa de nuevo sobre las versiones guardadas y no se pierde nada. Al revés
—dejar los comentarios solo adentro del `.xlsx` y confiar en la arqueología de XML más adelante—
sería poner lo más valioso en el lugar más frágil.

### Si el taller queda expuesto en internet

El taller **no tiene usuarios ni contraseña** — ver el aviso de `HOST` en `.env.example`. Cualquiera
que llegue puede lanzar ejecuciones y borrar ramas. Puertas afuera hay que ponerle autenticación
adelante (nginx, oauth2-proxy, lo que sea); esto vale para todo el sitio, no solo para la revisión.

Pero **dos rutas no pueden pedir autenticación**, porque quien las usa es el Document Server y no
tiene con qué autenticarse:

```
GET  /api/revision/{doc}/archivo     baja el archivo para abrirlo
POST /api/revision/{doc}/callback    avisa que el experto guardó
```

Esas dos hay que dejarlas pasar, y la segunda es la peligrosa: **sobrescribe el documento**. Por eso
cada documento tiene una **ficha** —un secreto de 32 bytes que viaja en la URL— y las tres rutas de
archivo la exigen: sin ella contestan `403`. El Document Server no necesita saber nada de esto; usa
las URLs que le damos.

La ficha reemplaza a JWT para este problema y no le pide nada a la otra punta. Lo que **no** hace es
proteger el resto del taller: eso es trabajo de la autenticación de adelante.

### Cómo se configura

Hace falta un [Document Server de OnlyOffice](https://github.com/ONLYOFFICE/DocumentServer). El
`podman-compose.yml` levanta uno para desarrollo; en un servidor que ya tenga el suyo, se apunta a
ese y se borra el servicio.

Si no hay ninguno configurado, el taller funciona igual: no aparece el botón y nada más.

Lo único delicado son las direcciones, que son **tres y no son la misma**:

```
navegador ─────── OO_URL_PUBLICA ──────→ Document Server     carga el editor
Document Server ─ OO_URL_DEL_TALLER ───→ taller              baja el archivo y avisa al guardar
taller ────────── OO_URL_INTERNA ──────→ Document Server     va a buscar lo que se guardó
```

La del medio es la que se escapa. El Document Server corre en otro contenedor, así que para él
`localhost` es él mismo, no el taller: si se le pone `http://localhost:8000`, el editor abre bien y
después el guardado no llega nunca. Con `podman compose` los servicios se ven por nombre
(`http://taller:8000`), y eso ya viene puesto en el compose.

En el `.env` solo hay que tocar `OO_URL_PUBLICA`.

> **Si el editor abre pero dice «Error de descarga»**, el Document Server está rechazando al taller
> por su propia protección anti-SSRF, que no acepta direcciones privadas — y dentro de la red de
> compose el taller es exactamente eso. Se resuelve con `ALLOW_PRIVATE_IP_ADDRESS=true`, que el
> compose ya trae. En su log se lo ve como *«DNS lookup … is not allowed. Because, It is private IP
> address»*.

### Esperá a que el Document Server esté sano antes de abrir el editor

Es la trampa más cara de este montaje, y no se parece en nada a su causa.

Su `/healthcheck` contesta `true` a los cinco segundos, pero **el servidor no está listo**: alrededor
de un minuto después termina de generar su caché de fuentes y **se reinicia solo**
(`documentserver-generate-allfonts.sh` hace `supervisorctl restart ds:docservice`). A quien abrió el
editor en esa ventana se le corta la sesión en plena carga — sale «Se ha perdido la conexión», o se
queda cargando sin fin, o el documento queda en solo lectura.

Medido acá: contenedor arriba a las 21:58:38, reinicio a las 21:59:51. **73 segundos.**

Por eso el `healthcheck` del compose no le cree al del servidor: además del HTTP, exige que el
contenedor lleve más de 120 segundos arriba. Mirá que diga `healthy` antes de abrir la revisión:

```bash
podman ps --filter name=onlyoffice --format "{{.Names}} {{.Status}}"
```

Mientras diga `(starting)`, el editor puede abrir y morirse a mitad de camino. No es tu navegador.

> Los plugins vienen apagados desde el taller (`editorConfig.plugins` en `main.py`). OnlyOffice
> arranca once por defecto —IA, OCR, editor de fotos, traductor, YouTube, Zotero…— que suman 1890
> archivos y no sirven para anotar una planilla. La primera apertura es mucho más liviana sin ellos,
> y esa es la que importa: cada reinicio del servidor cambia su huella y enfría la caché.

En desarrollo el Document Server corre **sin firma JWT** (`JWT_ENABLED=false`). Si el del servidor
la tiene activada, el secreto va en `OO_JWT_SECRETO`.

## Estado

La cadena completa (datos → ventaneo → características → filtrado → detección → eventos) anda de punta
a punta, con ramas, caché, borrado e inspección por etapa.

La revisión experta anda de punta a punta: el entregable se abre en el navegador, cada guardado deja
una versión y borrar una rama comentada avisa antes.

Pendiente: estabilidad Jaccard y feature-shift como etapas, comparar dos ramas lado a lado, y la
animación de la ventana deslizándose sobre la señal.

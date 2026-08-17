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

- el botón **★ Correr la de la tesis**,
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

Levanta un solo servicio. **No hay base de datos que levantar**: el árbol de ejecuciones es un archivo
SQLite y los resultados van a disco. Todo el estado es la carpeta de datos.

El repo de la tesis se monta en `/tesis` (escribible solo para que `pip install -e` genere
`src/tesis.egg-info`, que está en `.gitignore` de la tesis), así que la imagen no queda atada a una
versión del pipeline: en la interfaz siempre se muestra con qué commit se está ejecutando.

La primera vez hay que generar la tabla cruda dentro del contenedor:

```bash
podman compose run --rm taller python scripts/exportar_crudo.py
```

## Estructura

```
backend/
  etapas.py      definición de las 6 etapas y sus envoltorios sobre `tesis`
  almacen.py     SQLite (árbol) + caché en disco + hash de configuración
  trabajos.py    ejecución en segundo plano (una corrida tarda decenas de segundos)
  main.py        API y servidor de la web
web/
  index.html     página didáctica del proyecto
  taller.html    el banco de trabajo
  analisis.html  la pantalla de análisis de una rama
  app.js         formularios, árbol de ramas y qué se muestra en cada etapa
  analisis.js    los cuatro cortes de la pantalla de análisis
  grafico.js     el motor de gráficos, único que conoce la librería
  estilos.css    la paleta entera, en variables: un bloque por tema
  tema.js        el interruptor claro/oscuro (claro por defecto)
  vendor/        ECharts, versionado acá adentro (ver web/vendor/LEEME.md)
scripts/
  exportar_crudo.py   precalcula la tabla cruda desde el Excel de la tesis
tests/
  test_reproduccion.py  afirma los números de la tabla de verificación
data/                 estado local (ignorado por git): tabla cruda, caché, SQLite
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

**★ Correr la de la tesis** ejecuta las 6 etapas con la configuración con la que el trabajo reporta sus
resultados, para tener siempre una referencia contra la cual comparar. Las ramas que coinciden con esa
configuración quedan marcadas con ★.

**Borrar** elimina el paso seleccionado, todo lo que cuelga de él y sus resultados en disco.

## La pantalla de Análisis

El taller sirve para *operar*: configurar, ejecutar, ramificar. **Análisis** es para mirar una rama
ya corrida desde cuatro ángulos que el taller no muestra:

- **En qué coinciden los métodos.** Cuántos tramos marcan de a pares, y cuántos junta cada nivel de
  acuerdo. Es el argumento central del trabajo y hasta ahora vivía comprimido en un «4/5».
- **Cómo reparte los puntajes cada método**, un panel por método porque no son comparables entre sí,
  con el corte de candidatos marcado.
- **Si los candidatos están realmente aislados**, proyectando los tramos a dos dimensiones. Esa
  proyección es solo para mirar: no alimenta ninguna etapa.
- **Por qué se descartaron esas características**, con el mapa de correlación que la etapa de
  filtrado afirma pero no muestra.

Necesita una rama que llegue por lo menos al paso 5 (detección).

## Estado

La cadena completa (datos → ventaneo → características → filtrado → detección → eventos) anda de punta
a punta, con ramas, caché, borrado e inspección por etapa.

Pendiente: estabilidad Jaccard y feature-shift como etapas, exportar el Excel entregable desde el
taller, comparar dos ramas lado a lado, y la animación de la ventana deslizándose sobre la señal.

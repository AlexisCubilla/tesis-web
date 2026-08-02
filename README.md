# Taller — Etapa 1

Sitio didáctico y banco de experimentación de la Etapa 1 de la tesis *"Detección y clasificación de
anomalías en el consumo de baterías satelitales mediante un enfoque híbrido no supervisado-supervisado"*
(UNA–FPUNA; Cubilla, Recalde).

Dos cosas en una:

- **Una página que explica el proyecto** paso a paso, con gráficos y animaciones, para quien no conoce
  el trabajo.
- **Un taller** donde se puede cambiar cualquier parámetro del pipeline, ejecutarlo de verdad y
  comparar caminos. Cada cambio abre una **rama** que queda guardada.

> **El registro canónico de la tesis NO vive acá.** El código, las decisiones (ADR) y los resultados
> oficiales están en el repositorio de la tesis (`../repo-rebuild`). Este repo lo *usa* y lo *explica*;
> las ramas del taller son exploración, no resultados firmados.

## Cómo funciona

El backend **no reimplementa nada**: instala el paquete `tesis` del repo hermano y llama a sus
funciones. Si la web recalculara features o consolidara eventos por su cuenta, con el tiempo mostraría
números distintos a los de la tesis.

```
repo-rebuild/  (la tesis)          repo-web/  (este)
  src/tesis/        ──importa──→     backend/etapas.py   envuelve cada etapa
  data/raw/*.xlsx   ──lee 1 vez──→   data/crudo.joblib   tabla cruda precalculada
```

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

## Instalación (sin contenedor)

Requiere [mise](https://mise.jdx.dev) y que el repo de la tesis esté en `../repo-rebuild`.

```bash
mise install          # Python 3.11
mise run venv         # crea .venv
mise run install      # deps + el paquete `tesis` desde ../repo-rebuild
mise run datos        # lee el Excel una vez y precalcula la tabla cruda (~40 s)
mise run dev          # http://localhost:8000
```

## Con Podman

```bash
podman compose up
```

Levanta un solo servicio. **No hay base de datos que levantar**: el árbol de ejecuciones es un archivo
SQLite y los resultados van a disco. Todo el estado es la carpeta `data/`.

El repo de la tesis se monta de solo lectura en `/tesis`, así que la imagen no queda atada a una
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
  app.js         formularios, árbol de ramas y gráficos
scripts/
  exportar_crudo.py   precalcula la tabla cruda desde el Excel de la tesis
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

## Cómo se navega el taller

El punto que más confunde de una herramienta así es mezclar *mirar* con *cambiar*. Acá están separados:

- **El recorrido** (arriba) muestra las 6 etapas de la rama actual: cuáles están hechas, con qué
  configuración y cuál sigue. Se hace clic en cualquier etapa ya hecha para **inspeccionarla**.
- **La inspección** muestra los datos reales de esa etapa: la telemetría de una hoja, las ventanas
  dibujadas, qué características sobrevivieron al filtro, la distribución de puntajes de cada detector,
  la tabla de eventos (y al hacer clic en uno, sus tres señales).
- **El panel de ejecución** siempre apunta a la etapa *siguiente* a la que estás mirando, y avisa qué
  va a pasar: *continúa la rama actual* o *abre una rama nueva*.
- **Las ramas** (izquierda) listan cada camino completo, marcan cuál es la configuración oficial de la
  tesis y se pueden **borrar en cascada** (el nodo, todo lo que cuelga y sus resultados en disco).

El botón **Ejecutar la oficial** corre las 6 etapas con la configuración firmada de la tesis, para
tener siempre una referencia contra la cual comparar.

## Estado

La cadena completa (datos → ventaneo → características → filtrado → detección → eventos) anda de punta
a punta, con ramas, caché, borrado e inspección por etapa.

Pendiente: estabilidad Jaccard y feature-shift como etapas, exportar el Excel entregable desde el
taller, comparar dos ramas lado a lado, y la animación de la ventana deslizándose sobre la señal.

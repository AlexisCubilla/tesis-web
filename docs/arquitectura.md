# Decisiones de arquitectura

Por qué el taller está hecho así. Cada decisión con su alternativa descartada, en el espíritu de los
ADR del repo de la tesis.

---

## A1 — El backend no reimplementa el pipeline: importa `tesis`

**Decisión.** El paquete de la tesis se instala como dependencia (`pip install -e ../repo-rebuild`) y
cada etapa del taller es un envoltorio de diez líneas que arma un objeto de configuración y llama a la
función correspondiente.

**Por qué.** Si el taller recalculara features, consolidara eventos o seleccionara candidatos por su
cuenta, existirían dos implementaciones de la misma lógica. Se separarían con el tiempo y en algún
momento **el sitio mostraría números distintos a los de la tesis**. Eso sería peor que no tener sitio.

**Consecuencia.** El taller no puede exponer nada que el paquete no ofrezca. Cuando haga falta un
parámetro nuevo (por ejemplo, el interruptor de limpieza), el cambio va **en el repo de la tesis**, con
su ADR y su entrada de changelog — no acá.

**Verificación.** Con los valores por defecto el taller reproduce la corrida oficial exactamente:
24.138 filas, 6.102 ventanas, 45 características, 40 eventos, 3 en el límite.

---

## A2 — SQLite y archivos, no un servidor de base de datos

**Decisión.** El árbol de ejecuciones vive en un archivo SQLite (`data/ejecuciones.sqlite`). Los
resultados pesados (tensores, matrices, scores) van a disco con `joblib` (`data/cache/`), y en la base
solo queda la referencia.

**Por qué.** Son unos pocos miles de filas y un solo usuario a la vez. Un Postgres en contenedor
agregaría operación —credenciales, migraciones, un servicio más que puede fallar— sin agregar nada.
Con SQLite, **todo el estado es una carpeta**: se copia para respaldar y se borra para empezar de cero.

**Alternativa descartada.** Postgres tendría sentido con varios usuarios concurrentes o si esto viviera
en un servidor compartido. No es el caso.

**Regla.** Nunca guardar matrices dentro de la base. Los datos numéricos van a archivos.

---

## A3 — Las ramas emergen del hash, no se administran

**Decisión.** Cada nodo se identifica por `sha256(etapa + parámetros + clave del padre)`. Pedir una
configuración cuya clave ya existe devuelve el resultado guardado.

**Por qué.** Es lo que hace barato todo el proyecto. No hay que programar "ramificación": si dos
caminos comparten el tramo inicial, comparten las claves de ese tramo y por lo tanto el caché. Cambiar
la fracción de candidatos reutiliza ventanas, características y scores, y recalcula solo el final —
0,3 segundos en vez de 32.

**Detalle de implementación.** Los parámetros se serializan con las claves ordenadas, para que el orden
del diccionario no altere el hash.

**Antecedente.** Es la idea de `cache.py` en el repo de la tesis: *"nombres parametrizados por la
config para que cambiar un parámetro invalide solo lo afectado"*. Quedó escrito y sin usar; acá se usa.

---

## A4 — La tabla cruda se precalcula una vez

**Decisión.** Leer el Excel (~40 s) se hace una sola vez con `scripts/exportar_crudo.py`, y el taller
arranca desde esa tabla.

**Por qué.** Es el 40 % del costo de una corrida completa y no tiene ninguna decisión configurable
adentro. Precalcularlo ahorra esos 40 s en **cada** ejecución de **cada** rama.

**Trampa documentada.** Se guarda con `joblib` y **no** como CSV, porque `preprocessing.clean` detecta
los tramos contiguos buscando saltos en el índice original del Excel. Si el índice se pierde, los
segmentos salen mal **sin dar error**. Verificado: con `joblib` el índice se preserva y `clean`
devuelve exactamente lo mismo que partiendo del Excel.

**Qué queda configurable igual.** La selección de hojas y la limpieza, que son instantáneas (0,02 s) y
son decisiones de verdad. La limpieza en particular es el interruptor del hallazgo H1 de la tesis:
apagarla reproduce el camino del borrador previo (22.966 ventanas) y muestra en vivo cómo se derrumba
la estabilidad de HDBSCAN-GLOSH.

---

## A5 — Ejecución en segundo plano con un solo trabajador

**Decisión.** La petición encola el trabajo y devuelve la clave; un hilo lo ejecuta; el estado queda en
SQLite; el frontend pregunta cada tanto.

**Por qué.** Una corrida completa desde la tabla cruda tarda ~32 s: no entra en una petición HTTP.

**Por qué un solo trabajador.** Las etapas ya usan todos los núcleos internamente (los detectores
paralelizan con todos los hilos disponibles). Correr dos corridas a la vez solo las haría pelearse por
la CPU.

**Alternativa descartada.** Celery + Redis. Para un usuario a la vez es infraestructura sin beneficio.

---

## A6 — Frontend sin framework ni compilación

**Decisión.** HTML, CSS y JavaScript directos, servidos por el mismo backend. Los gráficos se dibujan
con Canvas y la animación de la órbita con SVG.

**Por qué.** Dentro de tres años esto se tiene que poder abrir y que funcione. Sin build, sin
`node_modules`, sin dependencias que se pudran. Y las animaciones que interesan —el satélite orbitando,
la ventana deslizándose sobre la señal— salen mejor con SVG y Canvas que con un framework.

**Costo aceptado.** Escribir a mano cosas que un framework daría hechas. Con el tamaño de este
frontend, conviene.

**Enmienda: una dependencia, congelada en el repositorio.** Los gráficos escritos a mano llegaron a
su techo, así que se incorporó ECharts. La regla no era «cero dependencias» sino «que dentro de tres
años esto se abra y funcione», y eso se sostiene porque la librería vive en `web/vendor/` como un
archivo más del repositorio: sin CDN —que desaparece o se corta sin internet— y sin `npm install`,
que traería `node_modules` y, tarde o temprano, un paso de compilación. El costo aceptado es el peso
en el repositorio y que actualizar sea manual. Un solo archivo del frontend, `grafico.js`, conoce la
librería; el resto pide gráficos por su nombre.

**Consecuencia operativa: el servidor manda `Cache-Control: no-cache` en todo lo que no sea la API.**
Sin build no hay huellas en los nombres de archivo (`app.4f2a1.js`) que inviten al navegador a
recargar, así que la frescura queda enteramente en manos de las cabeceras. Starlette manda `etag` y
`last-modified` pero **no** `Cache-Control`, y ante esa combinación el navegador aplica «frescura
heurística»: decide por su cuenta cuánto vale su copia y la sirve sin preguntar. Editar `web/` y
recargar dejaba entonces una pantalla con la versión nueva y la otra con la vieja — un síntoma feo de
diagnosticar, porque el servidor sí está entregando el archivo correcto. `no-cache` no prohíbe
guardar: obliga a revalidar.

---

## A7 — Separación explícita de lo canónico

**Decisión.** El taller muestra siempre con qué commit del repo de la tesis está corriendo, y la página
principal advierte que las ramas son exploración.

**Por qué.** El repo de la tesis tiene una regla central: hay **una** configuración consolidada y cada
cambio de parámetro se documenta en un ADR. Un sistema donde cualquiera cambia parámetros y guarda
corridas crea una segunda fuente de verdad que compite con ese registro. Si en una defensa alguien
pregunta *"¿esta tabla salió de la configuración firmada o de una corrida exploratoria?"*, tiene que
haber una respuesta inmediata.

**Resuelto.** La marca ★ distingue de un vistazo las ramas que coinciden con la configuración
oficial, tanto en el mapa como en el nombre de cada rama en la pantalla de análisis.

**Consecuencia al exportar: todo Excel que sale del taller abre con una hoja «Procedencia».**
Desde que el taller genera entregables, la pregunta de la defensa deja de ser hipotética: alguien
va a tener un archivo en la mano. Esa hoja va **primera** —es lo que se ve al abrir, no algo que
haya que ir a buscar— y dice si la rama coincide con la configuración de la tesis, cuál es su
clave, con qué commit del paquete se generó, la configuración completa paso por paso y, si se
aparta, en qué. El nombre del archivo también lo lleva: `..._tesis.xlsx` contra `..._rama-58ef8255.xlsx`,
para poder distinguirlos sin abrirlos.

**Trampa documentada.** Comparar los parámetros con la referencia serializándolos a JSON no
funciona: los valores salen del backend como float, pasan por el navegador —que tiene un solo tipo
numérico— y vuelven como entero, así que `percentil_baja_var=5` no coincidía con `5.0` y **la
configuración de la tesis aparecía apartándose de sí misma**. Todos sus Excel salían marcados como
exploratorios. La comparación es por valor, no por su texto, y hay tests que la cubren.

---

## A8 — Dos temas, una sola paleta

**Decisión.** Todo color del sitio es una variable CSS declarada en `web/estilos.css`, con dos
bloques: `:root` (tema claro, el de por defecto) y `:root[data-tema="oscuro"]`. Ningún otro archivo
escribe un color propio. Los `<canvas>`, que se pintan a mano y no heredan CSS, leen las mismas
variables con `getComputedStyle` en cada dibujo.

**Por qué el claro por defecto.** El sitio se muestra sobre todo de día, proyectado en una defensa o
recortado en capturas para el documento. Ahí el oscuro pierde. El oscuro queda como preferencia
explícita, guardada en `localStorage`. A propósito **no** se mira `prefers-color-scheme`: el claro es
el punto de partida para todos, no el que diga el sistema operativo.

**Trampa documentada (1).** El tema se aplica con un script inline en el `<head>` de cada página, no
desde `tema.js`. `tema.js` se carga al final del cuerpo, cuando el navegador ya pintó un cuadro: si
la decisión se tomara ahí, quien tiene el oscuro guardado vería un destello blanco en cada carga.

**Trampa documentada (2).** Como consecuencia de lo anterior, volver con «atrás» dejaba el tema
viejo: el navegador restaura la página entera desde el bfcache y el script del `<head>` **no** se
vuelve a ejecutar. Se veía como que el cambio funcionaba en una pantalla y en la otra no. `tema.js`
escucha `pageshow` con `event.persisted` y reaplica lo guardado, que es lo que manda — no lo que
quedó en el DOM. Por lo mismo escucha `storage`, para que dos pestañas abiertas no se contradigan.

**Excepción anotada.** El globo terráqueo y el satélite del inicio llevan colores fijos, fuera de la
paleta. Son el color de un objeto físico —la Tierra es azul de día y de noche—, así que cambiarlos
con el tema se vería mal. Lo que sí usa variables es el cielo de atrás y el anillo de la órbita.

**El héroe del inicio va siempre sobre fondo de espacio**, en los dos temas, y termina disolviéndose
en el fondo de la página. Eso no rompe la regla de un solo lugar para los colores: el bloque
`.cielo` **redefine** las mismas variables acotadas a él, así que el `h1`, la bajada y los botones
siguen escritos con `var(--texto)` sin enterarse de dónde están. La única salvedad es que `body`
resuelve `color: var(--texto)` una sola vez y los hijos heredan el color ya calculado, no la
variable: por eso `.cielo` también fija `color` explícitamente.

**Dónde NO va el universo.** El resto del inicio y todo el taller quedan sobre la paleta plana. En
el taller hay tablas, formularios y cinco curvas por gráfico: un fondo con textura compite con el
dato justo donde hay que leerlo, y arruina las capturas que van al documento — que es la misma razón
por la que el tema claro es el de por defecto.

---

## A9 — Los gráficos son instrumentos de lectura, no ilustraciones

**Decisión.** Cada gráfico tiene ejes rotulados con su unidad, muestra los valores al pasar el
puntero, deja acercarse a un tramo arrastrando, se abre en grande y tiene una tabla con los números
detrás. El motor está en `web/grafico.js`, sobre ECharts versionado en `web/vendor/`
(ver la enmienda del A6).

**Por qué.** Lo que había eran polilíneas sin un solo eje. Servían para reconocer una forma y nada
más: no se podía leer un valor, ni saber en qué medición ocurría algo, ni mirar de cerca un tramo
sospechoso — que es exactamente lo que uno quiere hacer en un banco de experimentación de detección
de anomalías.

**Tres señales, tres paneles.** Antes las tres iban encimadas en un mismo dibujo, cada una escalada
a su propio mínimo y máximo. Eso es un gráfico de dos ejes con los ejes escondidos: las alturas
relativas no significan nada y no hay forma de darse cuenta mirando. Ahora cada señal tiene su panel
con su escala y su unidad, y todos comparten el eje X. Se siguen comparando las formas —que era para
lo que servía— y además se leen los valores. Lo mismo con los cinco detectores en la etapa de
detección: cinco paneles, no cinco curvas encimadas.

**Consecuencia en el backend.** `get_datos` dejó de submuestrear la serie a 300 puntos. Acercarse
sobre una curva diezmada solo agranda la diezma: no aparece ni un dato nuevo. La hoja más grande
tiene ~1.100 mediciones, así que va entera y el submuestreo queda como red de contención.

**La paleta de series está verificada, no elegida a ojo.** Los cinco colores pasan un validador que
mide la separación entre pares vecinos, también simulando daltonismo. La paleta anterior tenía un
naranja y un ámbar a ΔE 1,1 en deuteranopía y 8,5 con visión normal — dos series que no se
distinguían ni con visión de color completa. Si se tocan esos valores hay que volver a validarlos.

**Lo que se evitó a propósito.** Nada de hacer zoom con la rueda del mouse sin más: rompe el
desplazamiento de la página, que es lo que la persona estaba haciendo. Hace falta tener Ctrl
apretado; para lo demás está la barra de rango y la herramienta de recuadro.

**Qué sobrevivió al cambio de librería.** Las decisiones de arriba son de contenido, no de
implementación: al pasar de Canvas a mano a ECharts se conservaron enteras. Lo que la librería
aportó fue terminación —globo, leyenda, barra de rango, exportar imagen, ver los datos en tabla— y
el catálogo de tipos que hizo posible el A10.

---

## A10 — Una pantalla aparte para analizar, separada de la de operar

**Decisión.** «Análisis» es una tercera pantalla, hermana de «El proyecto» y «Taller». Muestra
cuatro cortes de la rama que se elija: coincidencia entre detectores, distribución de puntajes,
dispersión de las ventanas en dos dimensiones y correlación entre características.

**Por qué separada.** El taller es para *operar*: configurar una etapa, ejecutarla, mirar qué
produjo y ramificar. Analizar es otra cosa —comparar, buscar por qué— y necesita gráficos grandes y
varios a la vez. Metidos dentro de la vista de fase alargaban una pantalla que ya es larga y
competían con los botones que hacen avanzar el pipeline.

**Qué agrega que no existía.** Sobre todo la **coincidencia entre métodos**, que es el argumento
central del trabajo —el acuerdo entre métodos que piensan distinto reemplaza a la respuesta correcta
que no existe— y hasta ahora vivía comprimido en un «4/5» dentro de una celda. Y el **mapa de
correlación**, que hace visible por qué la etapa de filtrado descarta lo que descarta, en vez de
mostrar dos listas de pastillas sin explicación.

**Dónde está el límite con A1.** La regla de «qué tramo está marcado» no se reimplementa: se le
pide al paquete de la tesis (`export._detector_candidates`, la misma que usa `build_candidate_table`),
justamente para no tener dos definiciones que se separen con el tiempo. Lo que el backend calcula es
solo presentación: contar intersecciones, armar histogramas, correlacionar columnas y proyectar.

**La proyección 2D es la excepción, y va anotada.** Es cálculo nuevo, hecho acá y no en la tesis.
Se acepta porque es **solo para mirar**: no alimenta ninguna etapa, no se guarda y ningún número del
trabajo depende de ella. La pantalla lo dice con todas las letras, para que nadie la confunda con el
detector PCA del pipeline, que sí es parte del método.

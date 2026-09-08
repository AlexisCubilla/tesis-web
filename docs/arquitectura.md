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
24.138 filas, 6.102 ventanas, 45 características, 40 eventos, 3 en el límite. Hay tests que lo
afirman (`mise run test`), porque una afirmación así no puede depender de que alguien la mire.

**Cómo se cumple, en concreto.** El paquete se instala con `pip install -e`, así que no hay copia:
`tesis.export.__file__` apunta al `.py` del repo de la tesis y editarlo ahí cambia lo que ejecuta el
taller en la petición siguiente. Las seis etapas, la selección de candidatos y los tres Excel del
entregable son llamadas a esas funciones.

**Dónde el backend sí calcula, y por qué se acepta.** Para dibujar hace falta más que lo que el
paquete expone: histogramas, percentiles, cajas, matrices de correlación y una proyección 2D. Todo
eso es *presentación* —descriptivo, no decide nada, no vuelve a ninguna etapa— y va anotado como tal
donde aparece.

**La excepción a vigilar.** El gráfico del filtrado dibuja el rango intercuartílico y su corte
replicando el criterio de `filtering.filter_low_variance`, aunque el motivo de cada descarte sí se
delega a esa función. Hoy coinciden. Si allá se cambia el criterio, las etiquetas seguirían bien y
las barras mostrarían una magnitud que el filtro ya no usa: un gráfico que parece correcto mientras
miente. Está marcado en el código con la advertencia de tocar ambos lados.

**Deuda anotada.** La salida de fondo es que el paquete devuelva qué medida y qué corte usó, en vez
de que el taller lo deduzca. Ese cambio va **en el repo de la tesis**, con su ADR — como manda la
consecuencia de arriba.

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

## A8 — Un solo tema oscuro, con el universo como identidad

**Decisión (revisada).** El sitio tiene **un** tema, oscuro, y no hay interruptor. Todo color vive
como variable CSS en un único bloque `:root` de `web/estilos.css`. Ningún otro archivo escribe un
color propio. Los `<canvas>`, que se pintan a mano y no heredan CSS, leen las mismas variables con
`getComputedStyle` en cada dibujo.

**Qué decía antes, y por qué se dio vuelta.** La primera versión tenía dos temas con el claro por
defecto, y el argumento era razonable: el sitio se proyecta de día y se recorta en capturas para el
documento, y ahí el oscuro pierde. Se revisó por dos motivos:

1. **El claro no aportaba nada que el oscuro no diera.** Era una segunda paleta completa —cuarenta y
   pico de variables duplicadas, más un juego de series validado aparte— manteniéndose al día para
   que el sitio se viera *igual pero más claro*. Nadie leía nada mejor.
2. **El interruptor traía una clase de errores propia**, y los tres se dieron: destello blanco al
   cargar si el tema guardado era el oscuro; el tema viejo al volver con «atrás», porque el bfcache
   restaura la página entera y el script del `<head>` no se vuelve a ejecutar; y dos pestañas
   abiertas contradiciéndose. Cada uno se arregló con más código —script inline en el `<head>`,
   `pageshow` con `event.persisted`, un escucha de `storage`—. Al no existir el interruptor,
   desaparecen los tres y se van con él `tema.js`, el script inline de las dos páginas y el
   `data-tema` del `<html>`.

**Lo que se acepta a cambio.** Proyectar un sitio oscuro en un aula con luz se lee peor, y las
capturas que van al documento entran en oscuro. Es el costo asumido a cambio de una sola paleta. El
juego claro queda en el historial de git si alguna vez hace falta.

**Dónde SÍ y dónde NO va la textura.** El campo de estrellas es global y muy tenue
(`--estrellas-op: .45`): eso es lo que hace que el universo sea la identidad del sitio y no un adorno
de la primera pantalla. La **nebulosa rica vive solo en el héroe** del inicio. Las superficies donde
se lee un dato —tarjetas, tablas, cajas de gráfico— son planas a propósito: una textura detrás de
cinco curvas compite con el dato justo donde hay que leerlo.

**Las tarjetas son planas, y la elevación está reservada.** `.tarjeta` no lleva degradado ni sombra.
El taller apila tres o cuatro, y con degradado más sombra cada panel competía por atención con los
gráficos que tenía adentro; un fondo parejo y un filete de 1 px alcanzan para separar. `--sombra`
sigue existiendo pero solo la usa el modal del gráfico, que es lo único que de verdad flota.

**Dos radios, no uno.** `--radio: 6px` para contenedores y `--radio-2: 4px` para lo que va anidado
adentro. Antes había un solo token de 12 px y media docena de valores sueltos entre 7 y 10: una caja
de 9 px dentro de otra de 12 px deja una esquina que se ve mal cortada.

**Los íconos van dibujados, no escritos.** Antes eran glifos en el contenido: `★` para la
configuración de la tesis, `＋`/`－` para los pliegues, `▸` para los cortes, `→` para el flujo de una
etapa a la otra. Cada sistema los dibuja distinto, no heredan el grosor de la fuente, quedan mal
alineados con la línea de base, y en algunas plataformas la estrella sale coloreada como emoji. Ahora
son SVG: como **máscara** (`--ico-mas`, `--ico-menos`, `--ico-chevron`) cuando el ícono lo pone un
`::before`, y como marcado (`.ico`, y los ayudantes `icoEstrella()` / `icoFlecha()` de `app.js`)
cuando va suelto. La máscara toma el color de quien la usa, así el ícono queda dentro de la paleta.
La flecha **en prosa** —«25.024 → 24.138 filas»— sigue siendo texto: ahí el signo significa «pasa a
ser», no es un ícono.

**Excepción anotada.** El globo terráqueo y el satélite del inicio llevan colores fijos, fuera de la
paleta. Son el color de un objeto físico —la Tierra es azul de día y de noche—, así que atarlos a las
variables no tendría sentido. Lo que sí usa variables es el cielo de atrás y el anillo de la órbita.

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

**Regla de poda: nada se dice dos veces.** Un gráfico que repite algo ya visible en pantalla no
suma, resta — hace que el resto pese menos. De ahí tres cortes concretos: los recuadros de números
ya no repiten lo que dice el recuadro «entra → sale» (24 recuadros pasaron a 7); el mapa de
correlación vive solo en la etapa de filtrado, que es donde explica algo, y no también en el
análisis; y la curva de percentiles de la etapa de detección se fue porque es la misma información
que el histograma del análisis —una acumulada y una densidad dicen lo mismo—, que además marca el
corte de candidatos.

**La explicación va bajo demanda, no siempre puesta.** La interfaz llegó a tener **1.975 palabras**
de prosa: un párrafo editorializando antes de cada gráfico, y los cinco títulos del análisis eran
preguntas —«¿En qué coinciden los métodos?», «¿Es acuerdo, o es duración?»…—, que no es estilo sino
una plantilla. El sitio es didáctico, así que la explicación no sobra; sobraba que estuviera siempre
delante. Ahora el título nombra, una línea dice **dónde mirar**, y el porqué se despliega para quien
lo busque. Quedan 188 palabras visibles.

**Guiar es señalar dentro del dibujo.** Un párrafo al lado no guía: compite. En «Acuerdo, o
duración» la banda y el rótulo del salto se **calculan** —el mayor entre dos grupos consecutivos, y
solo si supera un umbral—, no se escriben a mano, para que la anotación siga siendo cierta en
cualquier rama.

**Y no todo pesa igual.** En el análisis, los cortes que sostienen el argumento van abiertos y el
resto detrás de un pliegue. Con nueve gráficos del mismo peso visual no se distinguía el que puede
refutar la tesis del que está para mirar.

**Qué sobrevivió al cambio de librería.** Las decisiones de arriba son de contenido, no de
implementación: al pasar de Canvas a mano a ECharts se conservaron enteras. Lo que la librería
aportó fue terminación —globo, leyenda, barra de rango, exportar imagen, ver los datos en tabla— y
el catálogo de tipos que hizo posible el A10.

---

## A10 — El análisis es una pestaña de la vista de fase, no una pantalla aparte

**Decisión (revisada).** Los cuatro cortes de análisis —coincidencia entre detectores, distribución
de puntajes, dispersión de las ventanas y correlación entre características— viven en una pestaña
de la vista de fase del taller, junto a «Este paso». Aparece solo en los nodos que tienen puntajes
(detección y eventos).

**Qué decía antes, y por qué se dio vuelta.** La primera versión fue una tercera pantalla,
«Análisis», con el argumento de que el taller era para *operar* —configurar, ejecutar, ramificar— y
analizar era otra cosa. Ese argumento se cayó por dos lados:

1. **Se erosionó solo.** Después se le agregaron gráficos a las seis etapas, así que la vista de
   fase pasó a ser, en su mayor parte, mirar lo que salió. La frontera que justificaba separarlas
   dejó de existir.
2. **La separación tuvo un costo medible.** Elegir la rama desde el otro lado obligaba a
   reconocerla en un desplegable, y ahí una rama es apenas un texto: de seis ramas de una corrida
   normal, **cinco compartían etiqueta** con otra. Hubo que construir nombres por diferencias
   contra la referencia, una tira con la cadena y un `?nodo=` para compensarlo. Más de la mitad de
   `analisis.js` —247 de 469 líneas— existía solo para eso.

Dentro del taller nada de eso hace falta: el nodo ya está elegido sobre el mapa, que es donde una
rama se ve como lo que es, una bifurcación con su historia. Al fusionar **salió más código del que
entró**.

**Por qué pestañas y no todo junto.** La objeción válida de la propuesta original sigue en pie: la
vista de fase ya es larga y el mapa de correlación mide unos 760 px. Con pestañas se dibuja una
sola por vez, así que la altura no se suma.

**Qué muestra, y por qué no es lo mismo en los dos nodos.** Los cortes que salen de los puntajes
—coincidencia, distribución, dispersión, desplazamiento de características, correlación— son
idénticos en un nodo de detección y en su hijo de eventos, y tiene que ser así: la etapa de eventos
hace `salida = dict(entrada)` y solo agrega la tabla, así que los `scores` y las `filtradas` son los
mismos objetos. Verificado campo por campo.

Lo que sí es exclusivo de eventos es **«¿Es acuerdo, o es duración?»**, que sale de la tabla de
eventos y no existe un paso antes. Es el único gráfico del taller que puede **contradecir a la
tesis**: si los eventos de 4 y 5 métodos son sistemáticamente los más largos, ese número mide
duración antes que consenso, y el consenso es el argumento central del trabajo. La interfaz ya
advertía del confounder en un aviso de texto; mostrarlo era lo que faltaba.

**Descartado a propósito.** Un histograma de tamaños de evento. Diría lo que los recuadros ya dicen
(«18 eventos de una ventana», «3 en el límite») y lo que la línea de tiempo ya deja ver. Un gráfico
que repite algo que está en pantalla hace que el resto pese menos.

**Qué se conservó.** Los enlaces de la pantalla vieja siguen funcionando: `/taller?nodo=…&vista=analisis`
abre el nodo con la pestaña puesta, para poder guardar o proyectar un enlace directo.

**Dónde está el límite con A1.** No cambió con la mudanza. La regla de «qué tramo está marcado» se
le pide al paquete de la tesis (`export._detector_candidates`, la misma que usa
`build_candidate_table`), para no tener dos definiciones que se separen con el tiempo. Lo que el
backend calcula es solo presentación.

**La proyección 2D sigue siendo la excepción anotada.** Es cálculo nuevo, hecho acá y no en la
tesis. Se acepta porque es **solo para mirar**: no alimenta ninguna etapa, no se guarda y ningún
número del trabajo depende de ella. La pantalla lo dice con todas las letras, para que nadie la
confunda con el detector PCA del pipeline.

---

## A11 — Las rutas del frontend son relativas, para no atarse a la raíz del servidor

**Decisión.** Ninguna referencia del frontend empieza con `/`. Ni las hojas de estilo, ni los
scripts, ni los enlaces de navegación, ni las llamadas a la API: `estatico/estilos.css`,
`api/etapas`, `taller`, `.`. El navegador las resuelve contra la página actual, no contra la raíz.

**Por qué.** Una ruta absoluta obliga a que la aplicación viva en la raíz del dominio. Al montarla
detrás de un prefijo —`https://ejemplo.org/tesis/`— la portada carga pero pide `/estatico/estilos.css`,
que en ese servidor no es suyo. La alternativa habitual es un `<base href>` o una variable de
configuración con el prefijo; las dos agregan un valor que hay que acordar entre el servidor y el
código, y que se desincroniza en silencio. Las rutas relativas no necesitan que nadie declare nada:
desde `/taller` la llamada va a `/api/etapas`, desde `/tesis/taller` va a `/tesis/api/etapas`, y es
la misma línea de código.

**El riesgo concreto que evita.** No es un 404. Un servidor que aloja varias aplicaciones bajo
prefijos puede tener **su propio `/api`** apuntando a otro backend. Con rutas absolutas el taller no
falla por no encontrar sus archivos: le pega al servicio equivocado y recibe respuestas ajenas. Un
fallo silencioso, que es peor que uno ruidoso.

**La condición que lo sostiene, y cuándo se rompe.** Funciona porque **todas las páginas están a un
solo nivel** (`/` y `/taller`) y ninguna se sirve con barra final. Ahí `.` es el directorio de la
aplicación y `taller` es su hermano. Si algún día apareciera una ruta más profunda —`/taller/algo/`—
o la misma página respondiera con y sin barra final, las relativas se resolverían distinto según por
dónde se entró y esto deja de andar. Es el precio de no tener configuración: la restricción no está
declarada en ningún lado, vive en la forma de las URLs. Agregar un nivel de ruta obliga a revisar
esta decisión.

**Relación con A6.** Es la misma línea de pensamiento: sin compilación no hay paso que reescriba
rutas, así que la ruta que se escribe es la que se sirve. Que sea relativa es lo que permite
desplegar el mismo directorio en la raíz o bajo un prefijo sin tocar un archivo.

---

## A12 — El texto explicativo va en dos niveles

**Decisión.** Cada etapa y cada parámetro tienen dos textos: un **resumen** de una línea, siempre
visible, y el **desarrollo** completo detrás de un desplegable. La interfaz muestra el primero y deja
el segundo a un clic.

**Por qué.** El taller lo abre gente que no leyó la tesis, así que las explicaciones tienen que estar.
Pero la descripción de 80 palabras de una etapa aparecía **cada vez** que se miraba esa fase, la
número treinta igual que la primera, y una de las ayudas de parámetro llegaba a 106 palabras — un
párrafo entero adentro de un campo de formulario. Explicar de más y explicar de menos son el mismo
error visto desde dos lados; escalonar disuelve la disyuntiva en lugar de elegir un extremo.

**Medido.** De 1.249 palabras que estaban siempre a la vista se pasó a 262: **80 % menos texto en
pantalla sin borrar una sola palabra.** Todo lo que estaba escrito sigue estando, a un clic.

**Detalle deliberado:** el estado abierto **no** se recuerda. Al cambiar de fase se vuelve a plegar.
Si se recordara, bastaría con abrir un par de veces para volver al problema original.

**Alternativa descartada.** Acortar los textos. Habría perdido lo que los hace útiles —el hallazgo H1
en el interruptor de limpieza, el costo de la deduplicación, la trampa de leer el tope de evento como
si fueran hallazgos nuevos—, que es justamente lo que alguien de afuera no puede deducir solo.

---

## A13 — Dos ramas se comparan lado a lado, dentro de la misma vista

**Decisión.** Desde cualquier paso se puede elegir otro de la **misma etapa** y ver las dos
configuraciones y sus dos resultados en una tabla, con las filas que difieren resaltadas.

**Por qué.** Todo el diseño gira alrededor de ramificar —el hash encadenado (A3), el caché, el mapa
con bifurcaciones— pero hasta acá sólo se podía mirar **una rama por vez**. Para contrastar el 1 %
contra el 5 % había que abrir una, memorizar los números, abrir la otra y comparar de memoria. El
sistema sabía ramificar y no sabía **elegir**, que es para lo que uno ramifica.

**Sólo dentro de la misma etapa.** Comparar un ventaneo contra una detección no significaría nada: no
comparten ni parámetros ni métricas. El mapa resalta los pasos elegibles mientras se está eligiendo,
así la restricción se ve en lugar de explicarse.

**Se listan todas las filas, no sólo las que cambian.** Ver que quince parámetros son idénticos y uno
no es lo que permite **atribuir** la diferencia de resultado a ese cambio. Si se ocultaran las filas
iguales se perdería justamente el argumento; por eso las que difieren se resaltan y el resto queda
atenuado.

**Qué habilita.** La decisión que la tesis tiene abierta —qué fracción de tramos entregar al experto—
pasa a resolverse mirando una tabla:

| | 1 % | 5 % |
|---|---:|---:|
| eventos | 40 | 95 |
| con acuerdo de ≥4 métodos | 9 | 34 |
| que tocan el tope | 3 | 22 |

**Es exploración, no resultado firmado** (A7). La comparación ayuda a decidir; la decisión se firma
por ADR en el repositorio de la tesis, no acá.

---

## A14 — Dos columnas cuando hay lugar, una sola cuando no

**Decisión.** Con 1180 px o más de ancho **y el formulario abierto**, el taller se parte en dos: mapa
y fase a la izquierda, formulario fijo a la derecha. Por debajo de eso, o con el formulario cerrado,
todo va apilado en una columna.

**Por qué.** Apilado, abrir el formulario lo mandaba abajo del pliegue: se perdían de vista el mapa y
la fase justo cuando hacen falta para decidir qué valor poner. Configurar un paso es una tarea de
comparar contra lo que ya hay, no de completar campos a ciegas.

**Por qué sólo si el formulario está abierto.** La grilla se define con `:has(#panel-form.abierto)`.
Si se partiera siempre, con el formulario cerrado quedaría una columna vacía de 400 px y el contenido
apretado contra el margen izquierdo, sin nada a cambio.

**Relación con A6.** No hace falta JavaScript para esto: es una consulta de medios y un selector. El
estado que decide el ancho —si el formulario está abierto— ya vive en una clase del DOM.

---

## A15 — Las ramas se pueden nombrar, y el nombre no entra en el hash

**Decisión.** Cualquier paso acepta un nombre libre, que se muestra en el mapa y en la cabecera de la
fase. Se guarda en la columna `etiqueta` del árbol.

**Por qué.** El mapa identifica cada rama por su configuración: `50/1 · 0,95`. Es preciso y es
anónimo. Con diez ramas exploradas, poder llamar a una «la que le mostré a Jara» o «sin dedup» es lo
que la vuelve recuperable dos días después.

**El nombre convive con la configuración, no la reemplaza.** El mapa sigue mostrando los parámetros
debajo del nodo: hace falta ver en qué se diferencian dos ramas, y un nombre no lo dice.

**No entra en el hash (A3), a propósito.** Si entrara, renombrar generaría una clave distinta: crearía
una rama nueva y dejaría huérfano todo lo calculado. El nombre es una etiqueta para humanos, no parte
de la identidad del resultado — dos ramas con la misma configuración y distinto nombre son la misma
rama, y así se comportan.

---

## A16 — El taller pide sesión, y las dos rutas del Document Server quedan afuera

**Decisión.** Todo el sitio está detrás de usuario y contraseña (`backend/cuentas.py`). El
administrador se define en el `.env` y se siembra en cada arranque; el resto de las cuentas las crea
él desde `/usuarios`. La sesión es una cookie `HttpOnly` con un testigo opaco cuyo **hash** —no el
testigo— se guarda en la base.

**Por qué no alcanzaba con poner autenticación adelante.** Es lo que este documento recomendaba antes
(nginx, oauth2-proxy), y sigue siendo válido para *proteger*. Pero la clasificación de eventos
necesita algo que un proxy no da: **saber quién es cada uno adentro de la aplicación**. Dos revisores
tienen que poder opinar del mismo evento sin verse, y eso exige una identidad que llegue hasta la
consulta SQL. La reja y la identidad resultaron ser el mismo problema.

**Tres cosas quedan abiertas, y cada una por su motivo:**

| Ruta | Por qué |
|---|---|
| `/login`, `/api/sesion`, `/api/acceso` | Sin ellas no hay forma de iniciar sesión. |
| `/estatico/*` | Es el CSS y el JS —código, no datos— y la pantalla de ingreso lo necesita para dibujarse. |
| `/api/salud` | El healthcheck del contenedor no tiene con qué autenticarse. Devuelve `{"vivo": true}` y nada más; `/api/estado`, que sí cuenta la configuración, quedó cerrada. |
| `GET /api/revision/{doc}/archivo`<br>`POST /api/revision/{doc}/callback` | **Las usa el Document Server**, que corre en otro contenedor y no tiene credenciales. Su llave es la *ficha* del documento. Meterlas detrás de la sesión rompe la revisión experta de una forma que no se parece a su causa: el editor abre y el guardado no llega nunca. Hay un test que lo afirma. |

**Lo que esto NO cubre.** Los websockets del proxy de OnlyOffice no pasan por el middleware HTTP de
Starlette, así que quedan fuera de la sesión. Es un hueco angosto —hace falta la clave de un
documento, que solo se entrega a quien ya entró— pero está, y conviene que esté escrito.

---

## A17 — La clasificación de eventos es por persona y por rama, y se va con ella

**Decisión.** Doble clic sobre un evento —en la línea de tiempo o en la tabla— abre un diálogo con
las tres señales del tramo y una encuesta de cinco opciones más un comentario. La respuesta se guarda
en `data/revision/clasificacion.sqlite` con clave `(nodo, event_id, usuario)`.

**Por persona.** La coincidencia entre revisores independientes es lo único que, sin ground truth,
permite saber si la pregunta está bien planteada. Se pierde entera si el segundo revisor ve la
respuesta del primero, así que cada uno ve solo la suya.

**Por rama.** Un evento con otro umbral de dedup o con otra fracción de candidatos **no es el mismo
evento**: tiene otro rango, otras ventanas y otra prioridad. Heredarle la respuesta sería inventar un
juicio que nadie emitió. El costo asumido es que explorar ramas obliga a reclasificar, y se prefirió
ese costo antes que un dato que parece un juicio sin serlo.

**Borrar la rama borra sus clasificaciones**, y lo que protege el trabajo es el aviso previo: el
borrado en cascada se planta con un 409 que dice cuántos documentos del experto y cuántas
clasificaciones hay en juego, y exige confirmar. Las dos clases corren distinta suerte y el aviso lo
dice: el documento queda huérfano y se sigue bajando, la clasificación se va.

*Esta parte del ADR decía lo contrario, y se revirtió.* La fila sobrevivía a su rama, y seis columnas
copiaban hoja, segmento, rango, tramos y prioridad para que la respuesta siguiera siendo legible sin
ella. La analogía con `revision.py` no se sostuvo: ahí conservar funciona porque `GET /api/revision`
lista los documentos sin pasar por el árbol, y acá no existía la puerta equivalente. La única llave
para volver a una fila era su `nodo` —un hash de 16 caracteres que desaparece del árbol justo al
borrarlo— y no había listado de huérfanas ni pantalla que las mostrara. El dato se conservaba y era
inalcanzable salvo abriendo el SQLite a mano; las seis columnas se escribían en cada alta y no las
leía nadie.

Entre construir la mitad que faltaba o borrar de verdad, se eligió borrar, por coherencia con «por
rama» de más arriba: si el juicio pertenece a la corrida donde se emitió, sin esa corrida no hay
juicio que recuperar, hay una opinión sobre un identificador que ya no resuelve a nada. Las seis
columnas se quitaron con una migración que corre al arrancar (`clasificacion._migrar`).

**Un revisor puede retirar su propia respuesta.** El evento vuelve a estar sin clasificar, como si
nunca lo hubiera contestado. La clave incluye al usuario, así que nadie retira lo de otro, y por eso
no hace falta que sea privilegio de administrador. Se borra la fila en vez de marcarla como retirada
para que «sin clasificar» siga siendo **un solo estado**: con filas retiradas habría dos maneras de
no tener respuesta y las consultas del módulo tendrían que distinguirlas para siempre; la primera que
se olvidara contaría como respondido un evento que nadie respondió.

**Lo que no borra nada es dar de baja una cuenta.** Ahí el juicio queda, porque nadie eligió
deshacerse de él y sigue contando para la coincidencia entre revisores. La distinción entre los tres
casos es **quién decide**: su autor retirándolo, la rama entera yéndose con aviso, o un borrado
colateral que no debe llevárselo.

**Sin opción premarcada.** Ninguna de las cinco viene elegida, ni siquiera «Neutral». Un valor por
defecto se convierte en la respuesta de quien duda, y el reporte no podría distinguir «dijo neutral»
de «no contestó».

**Por qué la encuesta no reemplaza a la planilla de `revision.py`.** Son dos preguntas distintas. La
planilla no encajona al experto porque la taxonomía de la Etapa 2 es lo que él tiene que producir; la
encuesta hace la pregunta previa —¿esto es una anomalía?— que sí tiene respuesta cerrada y que hace
falta poder contar, comparar entre revisores y llevar a un reporte.

---

## A18 — El taller se mira sin cuenta; la sesión habilita escribir

**Decisión.** Cualquiera puede ver el proyecto, el mapa de ramas, los resultados, los gráficos, el
análisis y los tres entregables —incluida su descarga— sin iniciar sesión. La sesión pasa a ser lo
que habilita **escribir**: ejecutar el pipeline, crear, borrar o renombrar ramas, contestar la
encuesta y comentar en la revisión experta.

**Esto revierte media decisión del A16, a propósito.** Aquel ADR daba dos motivos para pedir sesión:
proteger los datos y atribuir el juicio. El segundo queda intacto —cada clasificación sigue firmada
por su revisor, y sigue siendo invisible para los demás—. El primero se cambia: un tutor, un
tribunal o un compañero tienen que poder ver el trabajo sin que haya que darles de alta, y darles
una cuenta para que solo miren es fricción sin contrapartida.

**Lo que esto significa, dicho sin eufemismos.** Si el taller se publica en internet, la telemetría
de BIRDS-4/TSURU y los resultados de las corridas son públicos. Es la consecuencia buscada. Quien
no la quiera tiene dos salidas que no cuestan código: no publicarlo fuera de la red local, o poner
autenticación por delante (nginx, un túnel) — que ahí sí sirve, porque el problema vuelve a ser
proteger y no identificar.

**La regla es por método, no por lista de rutas.** `_necesita_sesion` pide sesión para todo lo que
no sea `GET`/`HEAD`, con dos excepciones nombradas (crear y cerrar la sesión) y las dos rutas del
Document Server, que se resuelven antes. La razón es el sentido en que falla:

| Forma de escribirla | Cómo falla cuando alguien agrega un endpoint |
|---|---|
| Lista blanca de rutas abiertas | un endpoint de escritura nuevo queda **abierto** si nadie se acuerda de la lista |
| **Por método** (la elegida) | un endpoint de escritura nuevo nace **cerrado**; el olvido es dejar una lectura privada de más |

Las dos se pueden olvidar. La diferencia es qué pasa cuando se olvidan, y un olvido que cierra de
más se descubre solo —alguien reporta que no puede ver algo—, mientras que uno que abre de más no
se descubre nunca.

El precio es explícito y hay que sostenerlo: **un `GET` nuevo nace público.** Las lecturas que no
deban serlo van en `_LECTURAS_PRIVADAS`. Hoy son las cuentas, el editor del experto —abrirlo entrega
la ficha del documento, que es permiso de escritura disfrazado de lectura— y todo lo que termina en
`/clasificacion`, que responde «lo que dije yo» y sin un yo no tiene respuesta honesta.

**El frontend no dibuja lo que no se puede hacer.** Sin sesión no existen los botones de ejecutar,
borrar ni renombrar, ni la columna «mi juicio», ni el doble clic que abre la encuesta. Un botón que
falla al tocarlo es la peor forma de comunicar un permiso: parece que anda hasta que no anda. La
barra ofrece «Ingresar» en lugar de decir que falta autenticarse, porque no falta nada — el sitio
se está viendo entero.

**Un detalle que costó encontrar.** El interceptor de `api()` mandaba al ingreso ante cualquier
`401`, que era correcto cuando todo pedía sesión: significaba que había vencido. En modo lectura un
`401` es la respuesta normal a algo que necesita sesión, y redirigir expulsaba del taller a un
visitante por una petición que ni siquiera hizo a propósito. Ahora la distinción es explícita: se
redirige solo si *había* un usuario. «Se venció» y «nunca hubo» son cosas distintas.

## A19 — El catálogo es la Etapa 2.5, y por eso es del administrador

**Decisión.** Una pantalla nueva, `/catalogo`, reúne todo lo clasificado: qué respondió cada revisor
en cada evento, con nombre, más las cifras de cobertura y coincidencia. Pide rol administrador. La
revisión de los entregables (`/revision`) pasa al mismo rol.

**Son dos actividades distintas, no dos permisos.** La Etapa 2 es clasificar: un revisor mira un
evento en el paso 6 del taller y dice si le parece anómalo, de a uno y sin ver lo que respondieron
los demás. La 2.5 es lo que hace falta después y es otro trabajo: mirar el conjunto, ver dónde falta
un segundo juicio, y ver en qué coinciden y en qué no. Es el paso que convierte votos sueltos en un
catálogo, y la materia prima de la taxonomía que viene después.

**El rol protege el ciego por construcción.** El A17 apoya la Etapa 2 en la coincidencia entre
revisores independientes, y eso se pierde entero si el segundo ve la respuesta del primero. Hubo una
versión de este endpoint que devolvía «lo mío completo, y de los demás solo el reparto sin nombres»,
para que un revisor pudiera ver el conjunto sin romper nada. Se descartó: un filtro que hay que
acordarse de aplicar bien en cada consulta es más frágil que una pantalla a la que el revisor no
entra. El precedente estaba a la vista — `clasificacion.de_evento()` existe desde el principio y
ningún endpoint la usaba, justamente por este miedo.

**Por qué la revisión de entregables se mudó al mismo rol.** Los documentos que el experto comenta
a mano perdieron centralidad frente a la encuesta: la Etapa 2 pasó a ser la clasificación. Comentar
una planilla dejó de ser el trabajo del revisor, así que cerrar esa pantalla no le quita nada, y
agrupa las dos actividades de después-de-clasificar detrás del mismo rol.

**El rol se exige en la reja, no endpoint por endpoint.** `_necesita_admin()` resuelve por prefijo
de ruta, igual que `_necesita_sesion()` resuelve por método. Son once rutas entre las tres familias
—catálogo, cuentas, revisión— y con un `_administrador(request)` por función la número doce nace
abierta y nadie se entera; así nace cerrada.

*El precio son las excepciones, y hay que fijarlas con tests.* Cambiar la propia contraseña cuelga
de `/api/usuarios/{nombre}/contrasena`, así que el prefijo se la llevó puesta y un revisor dejó de
poder cambiar su clave. Lo encontró un test que ya existía. Ese endpoint tiene una regla más fina
que un rol —administrador **o** el dueño de la cuenta— y eso no se puede expresar donde solo se
conoce la ruta. Alcanza para «esta familia es del admin» y no para «esto es tuyo»; cuando aparezca
la segunda excepción, conviene revisar si la lista sigue siendo la herramienta.

**El HTML se sirve, la API corta.** `/catalogo` y `/revision` responden 200 a cualquier sesión y es
su propio pedido a la API el que devuelve 403. Cortar el HTML dejaría al revisor frente a una página
de error del servidor, fuera del taller; así llega a la pantalla y ella le explica qué es esto y que
su clasificación se hace en el paso 6. Y es 403 y no 401 a propósito: con 401 el frontend lo mandaría
a la pantalla de ingreso, donde volvería a entrar la misma persona y llegaría al mismo 401.

**Coincidir es caer del mismo lado, no marcar la misma casilla.** «Sí» y «Definitivamente sí» son la
misma respuesta con distinta convicción; contarlas como desacuerdo mediría la escala en lugar del
juicio. Se compara el signo del valor, que es para lo que la escala lo trae. Y un evento que miró una
sola persona no es acuerdo ni desacuerdo: queda afuera de la cifra, porque con cuarenta eventos
vistos por uno solo y dos por dos, meterlos en el mismo montón daría un 95 % que no describe nada.

**El reparto por revisor no es una cifra de calidad.** Si alguien dice «sí» al 90 % y otro al 10 %,
eso es un dato sobre cómo se entendió la pregunta, no sobre quién tiene razón. Se muestra sin nada
que sugiera un ranking.

**Se listan TODAS las ramas de eventos, no solo las clasificadas.** La primera versión recorría la
tabla de clasificaciones, así que una rama sin ningún juicio no tenía fila de dónde salir: con
cuatro ramas y una clasificada, el catálogo mostraba una sola mientras prometía decir «dónde falta
trabajo» — justo las ramas donde falta todo eran las invisibles. Ahora recorre el árbol y une.

**El orden: la tesis primero, después por trabajo hecho.** La rama de la tesis va arriba siempre; el
resto baja por cantidad de eventos clasificados, así adelante queda lo que ya tiene trabajo encima y
al final lo que no se tocó. Se desempata por total de eventos y después por clave — lo último no es
decorativo: sin un criterio final, dos ramas con el mismo trabajo pueden intercambiarse entre dos
cargas, y una lista que se reordena sola es difícil de leer.

*Y la ★ es la configuración de la tesis, no «tiene nombre».* Calcularla destapó un bug del A7:
`_diferencias_con_la_tesis` comparaba solo las claves que la configuración de referencia nombra, y
el taller tiene perillas propias que allá no existen —`filtrado.descartar`, que apaga el filtrado
entero—. Una rama que saltea un paso que la tesis necesita respondía «cero diferencias», y la hoja
de Procedencia del Excel escribía «SÍ — coincide en todos los parámetros» sobre ella: exactamente el
archivo indistinguible del oficial que el A7 existe para evitar. `app.js` ya recorría la unión de
claves y usaba el `defecto` de la etapa como valor esperado; la copia del backend se había quedado
atrás. Corregido y con tres tests que lo fijan.

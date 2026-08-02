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

---

## A7 — Separación explícita de lo canónico

**Decisión.** El taller muestra siempre con qué commit del repo de la tesis está corriendo, y la página
principal advierte que las ramas son exploración.

**Por qué.** El repo de la tesis tiene una regla central: hay **una** configuración consolidada y cada
cambio de parámetro se documenta en un ADR. Un sistema donde cualquiera cambia parámetros y guarda
corridas crea una segunda fuente de verdad que compite con ese registro. Si en una defensa alguien
pregunta *"¿esta tabla salió de la configuración firmada o de una corrida exploratoria?"*, tiene que
haber una respuesta inmediata.

**Pendiente.** Marcar visualmente cuál rama corresponde a la configuración oficial (ADR-0008: dedup
0,95, límite 15) para distinguirla de un vistazo.

# Dependencias versionadas

Acá viven las librerías de terceros, **con el archivo adentro del repositorio**. No es descuido:
es la única forma de usar una librería sin romper la promesa del ADR A6.

## Por qué el archivo está acá y no se instala

- **Nada de CDN.** El taller tiene que abrir sin internet —en una defensa, en una máquina
  aislada— y un CDN además desaparece o cambia de URL con los años.
- **Nada de `npm install`.** Eso traería `node_modules`, un `package.json` y, tarde o temprano, un
  paso de compilación. El A6 existe justamente para que dentro de tres años esto se abra y funcione.

El costo aceptado es el peso en el repositorio y que actualizar sea manual. Para un proyecto que se
va a consultar más de lo que se va a modificar, conviene.

## Qué hay

| Archivo | Versión | Licencia | Para qué |
|---|---|---|---|
| `echarts.min.js` | 5.6.0 | Apache-2.0 (`echarts.LICENSE`) | Todos los gráficos del taller y de la pantalla de análisis |
| `three.min.js` | r160, build UMD | MIT | El globo del héroe del inicio (`web/orbita3d.js`) |
| `tierra.png` | — | derivada de dominio público | La textura de ese globo |

### `three.min.js`

r160 y no una versión más nueva porque es de las últimas que publican build **UMD**: de r161 en
adelante el paquete es solo ESM, y un `<script src=...>` suelto dejaría de funcionar. Eso choca de
frente con el A6 —nada de paso de compilación—, así que la versión está fijada a propósito y subirla
no es «cambiar el número en la URL».

### `tierra.png`

Derivada de **Blue Marble: Land Surface, Shallow Water, and Shaded Topography**, NASA Earth
Observatory. Las imágenes de la NASA son de dominio público; la atribución va en el pie del dibujo.
<https://visibleearth.nasa.gov/images/57752/>

No es la imagen original: es una máscara de dos colores generada a partir de ella, clasificando cada
píxel en océano o tierra por `azul > rojo` y repintando con `--acento-hondo` y `--grafico-unico`. Dos
motivos, y el segundo es el que importa:

1. **Pesa 20 KB en lugar de 233.** Al ser exactamente dos colores, la PNG palettizada es una imagen
   de 1 bit disfrazada. Once veces menos que la JPEG original.
2. **Es la geografía real en la paleta del sitio.** Una Tierra fotorrealista sería el objeto más
   renderizado de una página cuyo chrome es monocromo y cuyas superficies son planas; así se queda la
   costa de verdad y el color de la casa.

Para regenerarla desde la original hay un bloque de código en el prototipo:
`web/proto/orbita-3d.html`, función `construirPaleta()` — hace lo mismo en el navegador.

## Cómo actualizar

```bash
curl -sSL -o web/vendor/echarts.min.js \
  https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js
```

Cambiando la versión en la URL. Después conviene correr `mise run test` y abrir las tres pantallas:
la librería se configura desde `web/grafico.js`, que es el único lugar que la conoce.

Para `three.min.js`, leer antes la nota de arriba sobre UMD:

```bash
curl -sSL -o web/vendor/three.min.js \
  https://unpkg.com/three@0.160.0/build/three.min.js
```

## Nota sobre el peso

El backend comprime con `GZipMiddleware` (`backend/main.py`), y estos archivos son texto, así que lo
que viaja por la red es bastante menos que lo que se ve acá:

| | en el repo | por la red |
|---|---|---|
| `echarts.min.js` | 1.010 KB | 327 KB |
| `three.min.js` | 654 KB | ~170 KB |
| `tierra.png` | 20 KB | 20 KB (ya comprimida) |

Sin el middleware, ECharts viajaba en 1,03 MB.

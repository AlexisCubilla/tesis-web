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

## Cómo actualizar

```bash
curl -sSL -o web/vendor/echarts.min.js \
  https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js
```

Cambiando la versión en la URL. Después conviene correr `mise run test` y abrir las tres pantallas
en los dos temas: la librería se configura desde `web/grafico.js`, que es el único lugar que la
conoce.

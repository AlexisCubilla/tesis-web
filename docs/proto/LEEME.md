# Prototipos de diseño

Exploraciones hechas el 2026-08-23 para decidir la identidad visual del sitio: tres direcciones
(«consola», «ficha», «órbita») probadas sobre la portada y sobre el taller, más los ensayos del globo
3D con distintas texturas, alturas de órbita y modelos de luz.

Se conservan como **registro del proceso**, no como código vivo. Lo que quedó elegido está en
`web/`; esto es de dónde salió.

## Por qué están acá y no en `web/`

El backend sirve **todo** el contenido de `web/` como estático. Si los prototipos vivieran ahí,
quedarían publicados junto con el sitio — visibles en la demo y navegables por cualquiera que
adivine la ruta. Como son material de trabajo y no parte de lo que se muestra, viven fuera de esa
carpeta.

## Cómo abrirlos

Directamente con el navegador (`file://`), empezando por `index.html`, que es el índice de las
variantes. Los enlaces entre ellos, `_base.css` y `vendor/` son relativos y funcionan así.

**Una salvedad:** algunos hacen `src="/estatico/vendor/echarts.min.js"`, una ruta absoluta contra el
servidor del taller. Abiertos como archivo suelto, esos gráficos quedan vacíos; el resto del
prototipo se ve igual. No se corrigió porque son un registro histórico y tocarlos los volvería otra
cosa que la que se evaluó ese día.

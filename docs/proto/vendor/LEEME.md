# Dependencias del prototipo de la órbita

Van vendorizadas y no por CDN por el mismo motivo que `web/vendor/echarts.min.js`:
el sitio tiene que poder servirse sin salida a internet, y una tesis no debería
depender de que un CDN siga existiendo dentro de cinco años.

## three.min.js

three.js r160, build UMD. MIT.
https://github.com/mrdoob/three.js — `LICENSE` en ese repo.

Se eligió r160 porque es de las últimas versiones que publican build UMD: de r161
en adelante el paquete es solo ESM, y un `<script>` suelto dejaría de funcionar.

## tierra-2048.jpg

«Blue Marble: Land Surface, Shallow Water, and Shaded Topography», NASA Earth
Observatory, 2048×1024 equirectangular.
https://visibleearth.nasa.gov/images/57752/blue-marble-land-surface-shallow-water-and-shaded-topography

DOMINIO PÚBLICO. Las imágenes de la NASA no tienen copyright y se pueden usar sin
permiso; la política pide atribuir a «NASA Earth Observatory», que es lo que hace
el pie del prototipo.

2048×1024 y no 4096×2048 a propósito: el globo se dibuja a 380 px de lado, así que
incluso al doble de densidad de píxel 2048 de ancho alcanza para la mitad visible
de la esfera. El de 4096 pesa cuatro veces y no se nota.

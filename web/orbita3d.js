/* ===========================================================================
   El globo del héroe, en three.js.

   MEJORA PROGRESIVA, y ese es el punto de todo el archivo. El SVG que ya existe
   sigue en el marcado y sigue siendo lo primero que se pinta: llega con el HTML,
   cuesta cero JavaScript y se ve completo antes de que este archivo exista. Solo
   si hay WebGL se descarga `three.min.js`, se arma la escena, aparece el lienzo y
   el SVG se retira. Si algo falla en cualquier punto de esa cadena —no hay WebGL,
   la librería no llega, la textura no carga—, el SVG se queda y no se nota nada.

   Por eso `three.min.js` NO se carga con un `<script>` en el HTML: se pide desde
   acá, y solo cuando ya se sabe que va a servir. Un equipo sin WebGL no baja los
   654 KB para nada.

   POR QUÉ VALE LA PENA. Dos cosas que el SVG no puede hacer:

     · Que el satélite pase por detrás del planeta lo resuelve el buffer de
       profundidad. En el SVG hacen falta dos copias del dibujo y dos animaciones
       de opacidad sincronizadas —ver el comentario largo en `index.html`—, y
       basta que una regla de CSS pise a la otra para que el satélite se quede
       quieto arriba parpadeando.
     · La inclinación es la real, 51,6°, la de un despliegue desde la ISS, en
       lugar de un aplastado de 0,42 elegido a ojo.

   LO QUE SIGUE SIN SER A ESCALA, y hay que decirlo:

     · El satélite. Un CubeSat 1U mide 10 cm contra 6.371 km de radio terrestre:
       a escala son 0,0000016 del globo, menos de una milésima de píxel. Está
       exagerado ~40.000 veces, y en el SVG también.
     · El radio orbital. A 400 km reales sería 1,063 veces el radio de la Tierra,
       o sea que la órbita raspa la superficie y no se ve. Está exagerada por el
       mismo motivo que la exageraba el SVG. `web/proto/orbita-3d.html` tiene un
       control para verla a escala y entender por qué.

   La paleta se lee de las fichas CSS, igual que hace `grafico.js`: así el globo
   sigue al sitio si el sitio cambia de color, y no hay un `#rrggbb` acá adentro.
   =========================================================================== */
(function () {
  'use strict';

  /* `.orbita-dibujo` y no `.orbita`: la primera es solo el cuadrado del dibujo, la
     segunda incluye el pie. Medir la caja equivocada daba un lienzo más alto que
     ancho y el globo salía achatado. */
  const caja = document.querySelector('.orbita-dibujo');
  if (!caja) return;

  const quieto = matchMedia('(prefers-reduced-motion: reduce)');

  /* Devolver el SVG. El script del `<head>` puso `globo3d` en el <html> y con eso
     el SVG quedó en `display: none`; quitarla lo trae de vuelta. Es el camino de
     rendición: se llama cuando la librería no llega, cuando el contexto WebGL no
     se puede crear, cuando la textura falla, o cuando el navegador pierde el
     contexto en caliente —que en un teléfono pasa de verdad—. */
  function rendirse() {
    document.documentElement.classList.remove('globo3d');
    const cv = caja.querySelector('.orbita-3d');
    if (cv) cv.remove();
  }

  /* La sonda de WebGL y la descarga de la librería viven en un script en línea en
     el `<head>` de `index.html`, no acá: así arrancan durante el parseo del HTML en
     lugar de esperar a que este archivo `defer` se ejecute. `window.__globo3d` es
     la promesa de que three.js cargó, o `null` si no hay WebGL.

     Antes esto estaba acá abajo y además esperaba a un IntersectionObserver para
     empezar a descargar. Para un dibujo que está en la primera pantalla, eso era
     latencia sin ninguna ganancia — y se notaba como un destello del SVG viejo.
     El observador se conserva más abajo, pero solo para lo que sirve de verdad:
     parar el bucle de dibujo cuando el globo sale de pantalla. */
  const listo3d = window.__globo3d;
  if (!listo3d) return;          // sin WebGL, el SVG se queda y no se pide nada
  listo3d.then(armar).catch(rendirse);

  // =======================================================================
  function armar() {
    const css = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
    const hex = (n, alt) => {
      const v = css(n);
      return /^#[0-9a-f]{6}$/i.test(v) ? new THREE.Color(v) : new THREE.Color(alt);
    };

    const cv = document.createElement('canvas');
    cv.className = 'orbita-3d';
    cv.setAttribute('aria-hidden', 'true');
    caja.appendChild(cv);

    let render;
    try {
      render = new THREE.WebGLRenderer({ canvas: cv, antialias: true, alpha: true });
    } catch (e) { rendirse(); return; }
    /* Pérdida de contexto en caliente: pasa en móviles cuando el sistema recupera
       memoria de la GPU. Sin esto quedaría un lienzo negro para siempre. */
    cv.addEventListener('webglcontextlost', (e) => { e.preventDefault(); rendirse(); });
    render.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
    render.setClearAlpha(0);   // el fondo lo pone la página, no la escena

    const escena = new THREE.Scene();
    /* La distancia de la cámara es lo que fija el tamaño del planeta en el cuadro,
       y se ajusta ACÁ y no encogiendo la esfera: si la esfera se achica y el radio
       orbital se queda, la exageración de la órbita empeora y el dibujo se vuelve
       menos fiel. Alejando la cámara todo se reduce parejo y la geometría no se
       toca.

       Medido con la trigonometría, no a ojo. Con el campo de visión en 32°:

         cámara            esfera    de alto    órbita    de alto
         (1,05 · 4,60)      24,5°       76 %     33,5°     105 %   ← se recortaba
         (1,20 · 5,25)      21,4°       67 %     29,5°      92 %   ← ahora

       O sea que el valor anterior no solo dejaba el planeta grande: la órbita se
       iba del cuadro por arriba y por abajo. Trece por ciento menos de diámetro
       aparente y la elipse entra completa, con margen.

       La proporción y/z se mantiene en 0,228 para que la inclinación con la que se
       ve el plano orbital no cambie. */
    const cam = new THREE.PerspectiveCamera(32, 1, 0.1, 100);
    cam.position.set(0, 1.20, 5.25);
    cam.lookAt(0, 0, 0);

    /* CASI PLANO, con la luz justa para que se lea esfera y no disco. Un material
       sin luz sobre una textura de dos colores da un círculo, no un planeta; un
       terminador marcado sería el objeto más renderizado de una página cuyo chrome
       es monocromo. El ambiente alto con una direccional suave es el punto medio:
       hay forma, no hay dramatismo. */
    /* `MeshLambertMaterial` y no `MeshStandardMaterial`, por costo de arranque.
       El estándar es el material PBR: compila el shader más caro de la librería,
       con rugosidad, metalicidad y un modelo de reflexión que acá no se usa para
       nada —la esfera es mate y la luz es un ambiente alto con una direccional
       suave—. Lambert da el mismo resultado visual en este caso y compila mucho
       menos código. En una GPU la diferencia es de milisegundos; en un equipo sin
       aceleración, que cae a rasterizado por software, es de cientos.

       La esfera baja de 96×64 a 64×44 segmentos: de ~12.000 triángulos a ~5.600.
       A 180 px de diámetro en pantalla el contorno ya era liso con la mitad. */
    const mat = new THREE.MeshLambertMaterial();
    const tierra = new THREE.Mesh(new THREE.SphereGeometry(1, 64, 44), mat);
    escena.add(tierra);
    escena.add(new THREE.AmbientLight(0xffffff, 0.86));
    const sol = new THREE.DirectionalLight(0xffffff, 0.95);
    sol.position.set(-1.6, 0.8, 2.9);
    escena.add(sol);

    /* La órbita: inclinación real. El radio SÍ está exagerado — ver la nota de
       arriba. 1,42 es el valor donde la elipse se lee entera sin que el satélite
       se vaya del encuadre. */
    const RADIO = 1.42;
    const grupo = new THREE.Group();
    grupo.rotation.z = THREE.MathUtils.degToRad(51.64);
    escena.add(grupo);

    const pts = [];
    for (let i = 0; i <= 256; i++) {
      const t = i / 256 * Math.PI * 2;
      pts.push(new THREE.Vector3(Math.cos(t) * RADIO, 0, Math.sin(t) * RADIO));
    }
    const anillo = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(pts),
      new THREE.LineDashedMaterial({
        color: hex('--acento', '#7fa8d6'), dashSize: 0.06, gapSize: 0.05,
        transparent: true, opacity: 0.72,
      })
    );
    anillo.computeLineDistances();   // sin esto el guionado no se dibuja
    grupo.add(anillo);

    /* Un CubeSat 1U es un cubo con dos antenas. No es el satélite de paneles
       grandes que dibujaba el SVG: un 1U no los tiene, y eso es un dato de la
       tesis y no una decisión de estilo. */
    const sat = new THREE.Group();
    sat.add(new THREE.Mesh(
      new THREE.BoxGeometry(0.075, 0.075, 0.075),
      new THREE.MeshLambertMaterial({ color: 0xc3ccd8 })
    ));
    const cara = new THREE.Mesh(
      new THREE.PlaneGeometry(0.06, 0.06),
      new THREE.MeshLambertMaterial({ color: hex('--acento-hondo', '#154473') })
    );
    cara.position.z = 0.0381;
    sat.add(cara);
    const matAnt = new THREE.MeshBasicMaterial({ color: 0xa8b6c6 });
    for (const sx of [-1, 1]) {
      const a = new THREE.Mesh(new THREE.CylinderGeometry(0.0026, 0.0026, 0.1, 6), matAnt);
      a.rotation.z = Math.PI / 2;
      a.position.x = sx * 0.086;
      sat.add(a);
    }
    grupo.add(sat);

    // --- la textura: última en llegar, y hasta entonces no se muestra nada ----
    new THREE.TextureLoader().load('estatico/vendor/tierra.png', (tex) => {
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = Math.min(4, render.capabilities.getMaxAnisotropy());
      mat.map = tex;
      mat.needsUpdate = true;
      listo();
    }, undefined, rendirse);   // si la textura no llega, vuelve el SVG

    // =====================================================================
    function medir() {
      const w = caja.clientWidth, h = caja.clientHeight;
      if (!w || !h) return false;
      render.setSize(w, h, false);
      cam.aspect = w / h;
      cam.updateProjectionMatrix();
      return true;
    }

    let visible = true, pedido = false, corriendo = false;
    const FASE_QUIETA = Math.PI * 1.35;   // el satélite entero, en la mitad cercana

    function dibujar(ms) {
      const t = ms / 1000;
      const fase = quieto.matches ? FASE_QUIETA : (t * 0.30) % (Math.PI * 2);
      sat.position.set(Math.cos(fase) * RADIO, 0, Math.sin(fase) * RADIO);
      sat.rotation.y = -fase + Math.PI / 2;
      tierra.rotation.y = quieto.matches ? 0.6 : t * 0.026;
      render.render(escena, cam);
    }
    function pedirCuadro() {
      if (pedido) return;
      pedido = true;
      requestAnimationFrame((ms) => { pedido = false; dibujar(ms); });
    }
    function bucle(ms) {
      if (!visible || quieto.matches) { corriendo = false; return; }
      dibujar(ms);
      requestAnimationFrame(bucle);
    }
    function seguir() {
      if (corriendo || quieto.matches || !visible) { pedirCuadro(); return; }
      corriendo = true;
      requestAnimationFrame(bucle);
    }

    function listo() {
      if (!medir()) return;
      /* El intercambio va en UN solo cuadro: se dibuja la escena, y en la misma
         vuelta el lienzo se hace visible y el SVG se retira. Ni un instante con las
         dos cosas encima —que era el destello— ni un instante con el hueco vacío. */
      dibujar(performance.now());
      cv.classList.add('visible');
      // El SVG NO se borra del marcado: está en `display: none` por la clase del
      // <html>, cuesta nada, y sigue siendo el respaldo si se pierde el contexto.

      new ResizeObserver(() => { if (medir()) pedirCuadro(); }).observe(caja);

      /* El bucle se corta al salir de pantalla. Sin esto, una pestaña abierta en
         otra sección sigue quemando GPU y batería para dibujar algo que nadie
         mira. */
      new IntersectionObserver((ents) => {
        visible = ents[0].isIntersecting;
        if (visible) seguir();
      }, { threshold: 0 }).observe(caja);

      quieto.addEventListener('change', seguir);
      seguir();
    }
  }
})();

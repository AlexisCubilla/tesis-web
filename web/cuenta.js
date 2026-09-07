/* La cuenta en la barra: quién está adentro, y cómo salir.
 *
 * Va en su propio archivo porque las cuatro pantallas del sitio tienen la misma barra pero cargan
 * scripts distintos: la didáctica no carga `app.js`, la de revisión tiene el suyo embebido. Una
 * copia del widget en cada una se habría desincronizado a la primera corrección.
 *
 * No pinta marcado nuevo en el HTML de cada página: busca el `<nav>` de la barra y se cuelga ahí.
 * Así agregar el widget a una pantalla nueva es agregar una etiqueta `<script>` y nada más.
 */
(function () {
  'use strict';

  const barra = document.querySelector('.barra');
  const nav = barra && barra.querySelector('nav');
  if (!barra || !nav) return;

  fetch('api/yo')
    .then((r) => (r.ok ? r.json() : null))
    .then((usuario) => (usuario ? pintar(usuario) : pintarIngresar()))
    .catch(() => {});   // sin red no hay nada útil que decir en la barra

  /* --- Sin sesión: una sola cosa, la puerta. -----------------------------------------------
     Antes decía además «Modo lectura». Se fue: «Ingresar» ya dice que no estás adentro, y el
     taller lo explica con todas las letras en su aviso. Dos elementos para un solo estado es
     una palabra de más en el lugar donde menos entra. */
  function pintarIngresar() {
    if (location.pathname.endsWith('/login')) return;

    const caja = document.createElement('div');
    // `sola`: un único elemento a la derecha no necesita filete que lo separe de nada.
    caja.className = 'cuenta sola';

    const destino = location.pathname.split('/').pop() + location.search;
    const entrar = document.createElement('a');
    entrar.className = 'boton';
    entrar.href = destino ? `login?destino=${encodeURIComponent(destino)}` : 'login';
    entrar.textContent = 'Ingresar';
    caja.appendChild(entrar);

    barra.appendChild(caja);
  }

  /* --- Con sesión: quién sos, y cómo salir. ------------------------------------------------
     La barra tiene dos zonas y cada una responde una pregunta distinta: a la izquierda A DÓNDE
     IR, a la derecha QUIÉN SOS. «Usuarios» es un destino, así que va con las otras pestañas y no
     acá — antes vivía en esta zona y saltaba de lado al entrar a esa pantalla, porque allá sí
     estaba escrito como pestaña. El mismo destino en dos lugares según dónde estés.

     Y «Salir» dejó de ser un botón con recuadro. Es lo que menos se usa de toda la barra y era lo
     más pesado de su zona; ahora pesa como el nombre que tiene al lado, que es lo que le
     corresponde. El recuadro queda reservado para los destinos. */
  function pintar(usuario) {
    if (usuario.rol === 'admin') agregarPestanaUsuarios();

    const caja = document.createElement('div');
    caja.className = 'cuenta';

    const quien = document.createElement('span');
    quien.className = 'quien';
    quien.textContent = usuario.nombre;
    quien.title = usuario.rol === 'admin' ? 'Administrador' : 'Revisor';
    caja.appendChild(quien);

    const salir = document.createElement('button');
    salir.type = 'button';
    salir.className = 'salir';
    salir.textContent = 'Salir';
    salir.addEventListener('click', async () => {
      salir.disabled = true;
      try {
        await fetch('api/sesion/salir', { method: 'POST' });
      } finally {
        location.href = '.';   // al proyecto: sin sesión sigue habiendo sitio que mirar
      }
    });
    caja.appendChild(salir);

    barra.appendChild(caja);
  }

  /** La pestaña de Usuarios, para el administrador, junto a las otras dos.
   *
   *  `usuarios.html` ya la trae escrita —y marcada como activa— así que ahí no se agrega nada:
   *  duplicaría el enlace, y además la escrita llega con la página en lugar de aparecer cuando
   *  responde `api/yo`. En las demás pantallas la pone esta función.
   */
  function agregarPestanaUsuarios() {
    if (nav.querySelector('a[href="usuarios"]')) return;
    const a = document.createElement('a');
    a.href = 'usuarios';
    a.textContent = 'Usuarios';
    nav.appendChild(a);
  }
})();

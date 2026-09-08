/* La esquina derecha de la barra: quién está adentro, el tema, y cómo salir.
 *
 * Va en su propio archivo porque las cinco pantallas del sitio tienen la misma barra pero cargan
 * scripts distintos: la didáctica no carga `app.js`, la de revisión tiene el suyo embebido. Una
 * copia del widget en cada una se habría desincronizado a la primera corrección.
 *
 * ES EL ÚNICO DUEÑO DE ESA ESQUINA. Antes `tema.js` inyectaba su botón ahí y este archivo el suyo,
 * sin conocerse; el resultado fue un interruptor que quedaba en medio de las pestañas y se movía al
 * navegar. Ahora `tema.js` ofrece la API (`window.Tema`) y acá se decide qué se dibuja.
 *
 * EL TEMA VA SUELTO; LA SESIÓN, ADENTRO. Son dos cosas distintas: el tema es una preferencia de
 * quien mira —la usa también quien entra sin cuenta— y la sesión es quién sos. Meter el tema en el
 * menú de la cuenta lo ataba a tener una, y lo dejaba a dos clics de algo que se prueba mirando.
 * Queda a la izquierda del avatar, así el control está en el mismo lugar haya sesión o no. Detrás
 * del avatar queda lo que sí es de la cuenta: el nombre, el rol y «Salir».
 *
 * No pinta marcado nuevo en el HTML de cada página: busca la `.barra` y se cuelga ahí. Agregar el
 * widget a una pantalla nueva es agregar una etiqueta `<script>` y nada más.
 */
(function () {
  'use strict';

  const barra = document.querySelector('.barra');
  const nav = barra && barra.querySelector('nav');
  if (!barra) return;

  const ICONO_SALIR = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9"/></svg>`;

  const ICONO_USUARIOS = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
      stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
    <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/>
    <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13A4 4 0 0 1 19 7a4 4 0 0 1-3 3.87"/></svg>`;

  fetch('api/yo')
    .then((r) => (r.ok ? r.json() : null))
    .then((usuario) => (usuario ? pintarMenu(usuario) : pintarSuelto()))
    .catch(() => {});   // sin red no hay nada útil que decir en la barra

  /** El botón de tema. Va en la barra en los dos casos, con o sin sesión.
   *
   *  No hace falta mantenerle el ícono al día: `tema.js` recorre todos los `.btn-tema` cada vez que
   *  aplica un tema —incluido el cambio desde otra pestaña—, y este ya está en el documento para
   *  entonces. Acá solo se pone el estado inicial, porque este botón nace después de que `tema.js`
   *  corrió. */
  function botonTema() {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn-tema';
    b.title = 'Cambiar de tema';
    b.setAttribute('aria-label', b.title);
    b.innerHTML = window.Tema ? (window.Tema.actual() === 'oscuro'
      ? window.Tema.ICONO_SOL : window.Tema.ICONO_LUNA) : '';
    b.addEventListener('click', () => window.Tema && window.Tema.alternar());
    return b;
  }

  /* --- Sin sesión: el tema y la puerta, a la vista. --------------------------------------- */
  function pintarSuelto() {
    const caja = document.createElement('div');
    caja.className = 'cuenta sola';
    caja.appendChild(botonTema());

    if (!location.pathname.endsWith('/login')) {
      const destino = location.pathname.split('/').pop() + location.search;
      const entrar = document.createElement('a');
      entrar.className = 'boton';
      entrar.href = destino ? `login?destino=${encodeURIComponent(destino)}` : 'login';
      entrar.textContent = 'Ingresar';
      caja.appendChild(entrar);
    }
    barra.appendChild(caja);
  }

  /* --- Con sesión: un avatar, y el resto adentro. ----------------------------------------- */
  function pintarMenu(usuario) {
    if (usuario.rol === 'admin') agregarPestana('catalogo', 'Catálogo');

    const caja = document.createElement('div');
    caja.className = 'cuenta';

    const disparador = document.createElement('button');
    disparador.type = 'button';
    disparador.className = 'avatar';
    disparador.setAttribute('aria-haspopup', 'menu');
    disparador.setAttribute('aria-expanded', 'false');
    disparador.title = usuario.nombre;
    // La inicial y no un ícono genérico: con varios revisores, el avatar dice de quién es la
    // sesión sin abrir nada, que es justamente lo que hay que poder ver de un vistazo cuando lo
    // que se guarda queda firmado con tu nombre.
    disparador.innerHTML = `<span aria-hidden="true">${
      (usuario.nombre.trim()[0] || '?').toUpperCase()}</span>`;
    disparador.setAttribute('aria-label', `Cuenta de ${usuario.nombre}`);

    const menu = document.createElement('div');
    menu.className = 'menu-cuenta';
    menu.setAttribute('role', 'menu');
    menu.hidden = true;

    const quien = document.createElement('div');
    quien.className = 'quien';
    quien.innerHTML = `<strong>${usuario.nombre}</strong><span>${
      usuario.rol === 'admin' ? 'Administrador' : 'Revisor'}</span>`;
    menu.appendChild(quien);

    /* «Usuarios» va acá y no en las pestañas. Las tres pestañas son los destinos del TRABAJO —el
       proyecto, el taller, el catálogo— y administrar cuentas no es uno: es del sistema, se toca
       una vez cada tanto, y puesta al lado de «Catálogo» le disputaba la atención a la pantalla que
       sí se usa. Detrás del avatar queda junto a lo otro que es de la cuenta y no del trabajo. */
    if (usuario.rol === 'admin') {
      const usuarios = document.createElement('a');
      usuarios.className = 'op';
      usuarios.setAttribute('role', 'menuitem');
      usuarios.href = 'usuarios';
      usuarios.innerHTML = `${ICONO_USUARIOS}<span>Usuarios</span>`;
      menu.appendChild(usuarios);
    }

    const salir = document.createElement('button');
    salir.type = 'button';
    salir.className = 'op';
    salir.setAttribute('role', 'menuitem');
    salir.innerHTML = `${ICONO_SALIR}<span>Salir</span>`;
    salir.addEventListener('click', async () => {
      salir.disabled = true;
      try {
        await fetch('api/sesion/salir', { method: 'POST' });
      } finally {
        location.href = '.';   // al proyecto: sin sesión sigue habiendo sitio que mirar
      }
    });
    menu.appendChild(salir);

    caja.appendChild(botonTema());
    caja.appendChild(disparador);
    caja.appendChild(menu);
    barra.appendChild(caja);

    /* Abrir y cerrar. El menú se cierra al elegir algo, al hacer clic afuera y con Escape; las tres
       son las salidas que la gente prueba, y una que falte se siente como que se trabó. */
    const abrir = (si) => {
      menu.hidden = !si;
      disparador.setAttribute('aria-expanded', String(si));
      if (si) menu.querySelector('.op').focus();
    };
    disparador.addEventListener('click', (e) => { e.stopPropagation(); abrir(menu.hidden); });
    menu.addEventListener('click', (e) => { if (e.target.closest('.op')) abrir(false); });
    addEventListener('click', (e) => { if (!caja.contains(e.target)) abrir(false); });
    addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || menu.hidden) return;
      abrir(false);
      disparador.focus();
    });
  }

  /** Una pestaña que solo ve el administrador. Hoy es una sola: «Catálogo».
   *
   *  `catalogo.html` ya trae la suya escrita y marcada como activa, así que la comprobación de
   *  duplicado no es defensiva: es lo que evita que ahí aparezca «Catálogo» dos veces. Y la escrita
   *  a mano llega con la página, en vez de aparecer recién cuando responde `api/yo`, que es lo que
   *  hace que la barra no salte en la pantalla propia.
   *
   *  «Usuarios» estuvo acá y se movió al menú del avatar: administrar cuentas no es un destino del
   *  trabajo, y al lado de «Catálogo» le disputaba la atención.
   */
  function agregarPestana(href, texto) {
    if (!nav || nav.querySelector(`a[href="${href}"]`)) return;
    const a = document.createElement('a');
    a.href = href;
    a.textContent = texto;
    nav.appendChild(a);
  }
})();

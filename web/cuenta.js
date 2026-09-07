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
 * CON SESIÓN, UN SOLO CONTROL. El nombre, el tema y «Salir» eran tres cosas sueltas en la barra
 * para algo que se toca una vez por sesión. Van dentro de un menú detrás del avatar, que es donde
 * la gente ya las busca. Sin sesión no hay avatar que apretar, así que quedan a la vista el tema y
 * «Ingresar» — que es la acción de esa pantalla y esconderla un clic no la ayuda.
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

  fetch('api/yo')
    .then((r) => (r.ok ? r.json() : null))
    .then((usuario) => (usuario ? pintarMenu(usuario) : pintarSuelto()))
    .catch(() => {});   // sin red no hay nada útil que decir en la barra

  /** Un botón de tema, para los casos en que no hay menú donde meterlo. */
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
    if (usuario.rol === 'admin') agregarPestanaUsuarios();

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

    const tema = document.createElement('button');
    tema.type = 'button';
    tema.className = 'op';
    tema.setAttribute('role', 'menuitem');
    const rotularTema = () => {
      const va = window.Tema && window.Tema.actual() === 'oscuro' ? 'claro' : 'oscuro';
      const ico = window.Tema
        ? (va === 'claro' ? window.Tema.ICONO_SOL : window.Tema.ICONO_LUNA) : '';
      tema.innerHTML = `${ico}<span>Tema ${va}</span>`;
    };
    rotularTema();
    tema.addEventListener('click', () => { window.Tema && window.Tema.alternar(); rotularTema(); });
    menu.appendChild(tema);

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
    menu.addEventListener('click', (e) => {
      // Cambiar el tema NO cierra: se puede querer probar los dos. Salir cierra solo, navegando.
      if (e.target.closest('.op') === salir) abrir(false);
    });
    addEventListener('click', (e) => { if (!caja.contains(e.target)) abrir(false); });
    addEventListener('keydown', (e) => {
      if (e.key !== 'Escape' || menu.hidden) return;
      abrir(false);
      disparador.focus();
    });
  }

  /** La pestaña de Usuarios, para el administrador, junto a las otras dos.
   *
   *  `usuarios.html` ya la trae escrita —y marcada como activa— así que ahí no se agrega nada:
   *  duplicaría el enlace, y además la escrita llega con la página en lugar de aparecer cuando
   *  responde `api/yo`. En las demás pantallas la pone esta función.
   */
  function agregarPestanaUsuarios() {
    if (!nav || nav.querySelector('a[href="usuarios"]')) return;
    const a = document.createElement('a');
    a.href = 'usuarios';
    a.textContent = 'Usuarios';
    nav.appendChild(a);
  }
})();

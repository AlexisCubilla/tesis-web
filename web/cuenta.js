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

  const nav = document.querySelector('.barra nav');
  if (!nav) return;

  fetch('api/yo')
    .then((r) => (r.ok ? r.json() : null))
    .then((usuario) => { if (usuario) pintar(usuario); })
    .catch(() => {});   // sin sesión el middleware ya redirige; acá no hay nada que decir

  function pintar(usuario) {
    const caja = document.createElement('div');
    caja.className = 'cuenta';

    if (usuario.rol === 'admin' && !location.pathname.endsWith('/usuarios')) {
      const admin = document.createElement('a');
      admin.href = 'usuarios';
      admin.textContent = 'Usuarios';
      caja.appendChild(admin);
    }

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
        location.href = 'login';
      }
    });
    caja.appendChild(salir);

    nav.appendChild(caja);
  }
})();

/* Tema claro / oscuro.
 *
 * El claro es el de por defecto: el sitio se usa sobre todo de día, proyectado o impreso en
 * capturas, y ahí el oscuro pierde. El oscuro queda como preferencia explícita del que lo elige.
 *
 * POR QUÉ EL TEMA SE APLICA EN EL <head> Y NO ACÁ. Este archivo se carga al final del cuerpo, así
 * que para cuando corre el navegador ya pintó al menos un cuadro. Si la elección del tema se
 * resolviera acá, quien tiene el oscuro guardado vería un destello blanco en cada carga. Por eso
 * cada página lleva un script inline mínimo en el <head> que solo hace esto:
 *
 *     document.documentElement.dataset.tema = localStorage.getItem('tema') || 'claro'
 *
 * y este archivo se ocupa del resto: el botón, guardar la elección y avisarle al que dibuja.
 *
 * A propósito NO se mira `prefers-color-scheme`: el pedido es que el claro sea el de por defecto
 * para todo el mundo, no el que diga el sistema.
 */

(() => {
  const CLAVE = 'tema';
  const raiz = document.documentElement;

  const actual = () => (raiz.dataset.tema === 'oscuro' ? 'oscuro' : 'claro');
  const guardado = () => {
    try { return localStorage.getItem(CLAVE); } catch { return null; }
  };

  /** Deja el documento en un tema. No persiste: eso lo hace `elegir`. */
  function aplicar(tema) {
    raiz.dataset.tema = tema;

    for (const b of document.querySelectorAll('.btn-tema')) {
      const destino = tema === 'oscuro' ? 'claro' : 'oscuro';
      b.title = `Cambiar al tema ${destino}`;
      b.setAttribute('aria-label', b.title);
      b.setAttribute('aria-pressed', String(tema === 'oscuro'));
    }

    // Lo que se dibuja a mano (los gráficos en <canvas>) no hereda las variables CSS: hay que
    // volver a pintarlo. `taller.html` escucha este evento; `index.html` no lo necesita porque
    // todo lo suyo es SVG y CSS.
    dispatchEvent(new CustomEvent('tema-cambiado', { detail: { tema } }));
  }

  /** Cambia el tema por decisión de la persona: aplica y guarda. */
  function elegir(tema) {
    try { localStorage.setItem(CLAVE, tema); } catch { /* navegación privada: se pierde, no rompe */ }
    aplicar(tema);
  }

  for (const b of document.querySelectorAll('.btn-tema')) {
    b.addEventListener('click', () => elegir(actual() === 'oscuro' ? 'claro' : 'oscuro'));
  }

  /* Volver con «atrás» restaura la página entera desde el bfcache: el DOM vuelve tal cual estaba y el
     script del <head> NO se ejecuta de nuevo. Sin esto, cambiar el tema en una pantalla y volver a la
     otra con el botón del navegador mostraba el tema viejo, y parecía que el cambio funcionaba en una
     página y en la otra no. Lo que manda es lo guardado, no lo que quedó en el DOM. */
  addEventListener('pageshow', (e) => { if (e.persisted) aplicar(guardado() || 'claro'); });

  /* Y si el sitio está abierto en dos pestañas, que la segunda siga a la primera. */
  addEventListener('storage', (e) => {
    if (e.key === CLAVE && e.newValue) aplicar(e.newValue);
  });

  // Deja los rótulos del botón coherentes con el tema que puso el script del <head>.
  aplicar(actual());
})();

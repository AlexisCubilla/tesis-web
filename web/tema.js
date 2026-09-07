/* Tema oscuro / claro.
 *
 * EL OSCURO ES EL DE POR OMISIÓN. El universo es la identidad del sitio y así se ve la primera vez
 * que alguien entra. El claro es una preferencia explícita, y existe por el motivo que el ADR A8
 * daba a favor del claro antes de darlo vuelta: el taller se proyecta en aulas con luz y se recorta
 * en capturas que van al documento impreso, y ahí el oscuro pierde.
 *
 * POR QUÉ EL TEMA SE APLICA EN EL <head> Y NO ACÁ. Este archivo se carga al final del cuerpo, así
 * que para cuando corre el navegador ya pintó al menos un cuadro. Si la elección del tema se
 * resolviera acá, quien tiene el oscuro guardado vería un destello blanco en cada carga. Por eso
 * cada página lleva un script inline mínimo en el <head> que solo hace esto:
 *
 *     document.documentElement.dataset.tema = localStorage.getItem('tema') || 'oscuro'
 *
 * y este archivo se ocupa del resto: el botón, guardar la elección y avisarle al que dibuja.
 *
 * A propósito NO se mira `prefers-color-scheme`: el oscuro no es una preferencia de sistema acá, es
 * la identidad del sitio. Quien quiera el claro lo pide, y esa elección se guarda.
 *
 * LAS TRES FALLAS QUE EL A8 LE ACHACABA AL INTERRUPTOR están resueltas acá abajo, cada una con su
 * comentario: el destello al cargar (script en el `<head>`), el tema viejo al volver con «atrás»
 * (`pageshow` con `event.persisted`) y dos pestañas en desacuerdo (escucha de `storage`). Se
 * reponen juntas o no se repone ninguna: cada una sola deja un agujero que parece intermitente.
 */

/* Los dos íconos, en el lenguaje de trazo del sitio: se muestra el tema AL QUE SE VA, no el que
   está puesto. Un sol en el tema oscuro significa «pasar al claro». */
const ICONO_SOL = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
    stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.2"/>
  <path d="M12 2.6v2.2M12 19.2v2.2M4.2 12H2M22 12h-2.2M6.3 6.3 4.8 4.8M19.2 19.2l-1.5-1.5M17.7 6.3l1.5-1.5M4.8 19.2l1.5-1.5"/></svg>`;
const ICONO_LUNA = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  <path d="M20 14.4A8.4 8.4 0 0 1 9.6 4 8.4 8.4 0 1 0 20 14.4z"/></svg>`;

(() => {
  const CLAVE = 'tema';
  const raiz = document.documentElement;

  const actual = () => (raiz.dataset.tema === 'claro' ? 'claro' : 'oscuro');
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
      b.innerHTML = tema === 'oscuro' ? ICONO_SOL : ICONO_LUNA;
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

  /* ESTE ARCHIVO YA NO DIBUJA NADA. Antes inyectaba su propio botón en la barra, y `cuenta.js`
     inyectaba el suyo al lado: dos archivos poniendo controles en la misma esquina sin conocerse,
     que es como el interruptor terminó primero en medio de las pestañas. Ahora la esquina tiene un
     solo dueño —`cuenta.js`— y acá queda lo que solo este archivo sabe hacer: cuál es el tema,
     cómo cambiarlo, y las tres fallas del A8. */
  window.Tema = {
    actual,
    alternar: () => elegir(actual() === 'oscuro' ? 'claro' : 'oscuro'),
    /** Para que el menú pueda decir a qué tema lleva, sin duplicar los íconos. */
    ICONO_SOL, ICONO_LUNA,
  };

  for (const b of document.querySelectorAll('.btn-tema')) {
    b.addEventListener('click', () => elegir(actual() === 'oscuro' ? 'claro' : 'oscuro'));
  }

  /* Volver con «atrás» restaura la página entera desde el bfcache: el DOM vuelve tal cual estaba y el
     script del <head> NO se ejecuta de nuevo. Sin esto, cambiar el tema en una pantalla y volver a la
     otra con el botón del navegador mostraba el tema viejo, y parecía que el cambio funcionaba en una
     página y en la otra no. Lo que manda es lo guardado, no lo que quedó en el DOM. */
  addEventListener('pageshow', (e) => { if (e.persisted) aplicar(guardado() || 'oscuro'); });

  /* Y si el sitio está abierto en dos pestañas, que la segunda siga a la primera. */
  addEventListener('storage', (e) => {
    if (e.key === CLAVE && e.newValue) aplicar(e.newValue);
  });

  // Deja los rótulos del botón coherentes con el tema que puso el script del <head>.
  aplicar(actual());
})();

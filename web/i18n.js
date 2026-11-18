/* Idioma: español o inglés.
 *
 * DOS IDIOMAS Y NO N, Y POR ESO SIN CLAVES. El sitio se escribe en español y el inglés va AL LADO
 * de cada texto, no en un diccionario aparte:
 *
 *   - en el HTML, un atributo junto al texto:   <h1 data-en="Sign in">Ingresar</h1>
 *     (y `data-en-title`, `data-en-placeholder`, `data-en-aria-label` para los atributos);
 *   - en el JS, el par en la misma llamada:       I18n.t('Guardado', 'Saved')
 *
 * Un diccionario con claves (`login.titulo`) obliga a ir a otro archivo para saber qué dice una
 * pantalla, y este código se lee mucho más de lo que se traduce: los comentarios explican CADA
 * frase de la interfaz y tienen que poder verla. Con dos idiomas, el par en el lugar alcanza. Si
 * algún día hay un tercero, el cambio es mecánico: cada par pasa a ser una clave.
 *
 * SE CARGA EN EL <head>, SIN `defer`, por lo mismo que el tema: decide el idioma antes del primer
 * cuadro. Si el idioma es inglés, oculta el cuerpo hasta haber traducido el HTML estático; sin eso
 * quien eligió inglés vería un destello en español en cada carga. Si este archivo no llegara a
 * cargar no se oculta nada: la página queda en español, que es como está escrita.
 *
 * CAMBIAR DE IDIOMA RECARGA LA PÁGINA. Gran parte del texto lo arma el JS al pintar —tablas,
 * gráficos, diálogos—, y repintar todo en caliente sería tocar cada función que escribe texto.
 * Recargar es lo que hace la mayoría de los sitios, y no pierde nada: lo que se clasifica se guarda
 * al momento.
 *
 * EL IDIOMA TAMBIÉN VA EN UNA COOKIE, además de `localStorage`, para que el backend lo vea en cada
 * pedido sin que cada `fetch` tenga que mandarlo: los mensajes de error y los textos de las etapas
 * salen de allá.
 *
 * Por omisión, ESPAÑOL PARA TODOS, igual que el tema arranca en oscuro: el sitio está escrito en
 * español y así se ve la primera vez. No se mira el idioma del navegador; quien quiera inglés lo
 * pide con el selector, y esa elección se guarda.
 */
(() => {
  'use strict';
  const CLAVE = 'idioma';
  const raiz = document.documentElement;

  /* Lo guardado, y si `localStorage` está bloqueado, la cookie: sin ese respaldo, en navegación
     privada elegir inglés recargaría la página otra vez en español. */
  const guardado = () => {
    try { const v = localStorage.getItem(CLAVE); if (v) return v; } catch { /* sigue a la cookie */ }
    const m = document.cookie.match(/(?:^|;\s*)idioma=(es|en)\b/);
    return m ? m[1] : null;
  };
  const valido = (i) => (i === 'en' || i === 'es' ? i : null);

  const idioma = valido(guardado()) || 'es';
  raiz.lang = idioma;
  document.cookie = `${CLAVE}=${idioma}; path=/; max-age=31536000; SameSite=Lax`;

  /** El texto en el idioma de la página: `t('Guardado', 'Saved')`. */
  const t = (es, en) => (idioma === 'en' ? en : es);

  const ATRIBUTOS = ['title', 'placeholder', 'aria-label', 'alt'];

  /** Pasa al inglés el HTML marcado con `data-en*` dentro de `nodo`. En español no hace nada:
   *  el texto ya está escrito así. */
  function traducir(nodo = document) {
    if (idioma !== 'en') return;
    for (const el of nodo.querySelectorAll('[data-en]')) el.innerHTML = el.dataset.en;
    for (const a of ATRIBUTOS) {
      for (const el of nodo.querySelectorAll(`[data-en-${a}]`)) {
        el.setAttribute(a, el.getAttribute(`data-en-${a}`));
      }
    }
  }

  /** Cambia el idioma por decisión de la persona: guarda y recarga. */
  function elegir(nuevo) {
    if (!valido(nuevo) || nuevo === idioma) return;
    try { localStorage.setItem(CLAVE, nuevo); } catch { /* navegación privada: queda la cookie */ }
    document.cookie = `${CLAVE}=${nuevo}; path=/; max-age=31536000; SameSite=Lax`;
    location.reload();
  }

  window.I18n = {
    idioma,
    t,
    traducir,
    elegir,
    /** El idioma al que lleva el selector, que es lo que muestra (como el ícono del tema). */
    otro: idioma === 'en' ? 'es' : 'en',
    /** Para `toLocaleString` y `toLocaleTimeString`. */
    locale: idioma === 'en' ? 'en' : 'es',
  };

  if (idioma === 'en') {
    // Oculto hasta traducir. Por clase y no por estilo en línea, así el respaldo de abajo la saca.
    const estilo = document.createElement('style');
    estilo.textContent = 'html.i18n-pendiente body { visibility: hidden; }';
    document.head.appendChild(estilo);
    raiz.classList.add('i18n-pendiente');
    const mostrar = () => raiz.classList.remove('i18n-pendiente');
    document.addEventListener('DOMContentLoaded', () => { traducir(); mostrar(); });
    // Si algo del cuerpo revienta antes de DOMContentLoaded, la página no puede quedar en blanco.
    setTimeout(mostrar, 2000);
  }

  /* Volver con «atrás» restaura la página desde el bfcache sin correr este archivo. Si mientras
     tanto se cambió el idioma en otra pantalla, esta quedaría en el viejo: se recarga. */
  addEventListener('pageshow', (e) => {
    if (e.persisted && (valido(guardado()) || 'es') !== idioma) location.reload();
  });
})();

/* Barra para saltar entre los seis prototipos. Andamio del ejercicio. */
(function () {
  const P = [
    ['orbita',  'Órbita'],
    ['ficha',   'Ficha'],
    ['consola', 'Consola'],
  ];
  const aqui = location.pathname.split('/').pop();
  const dir = (aqui.split('-')[0]) || 'orbita';
  const pag = aqui.includes('taller') ? 'taller' : 'landing';

  const c = document.createElement('div');
  c.id = 'saltar';
  c.innerHTML = '<b>dirección</b>'
    + P.map(([k, n]) => `<a href="${k}-${pag}.html"${k === dir ? ' aria-current="page"' : ''}>${n}</a>`).join('')
    + '<span></span><b>página</b>'
    + ['landing', 'taller'].map((p) =>
        `<a href="${dir}-${p}.html"${p === pag ? ' aria-current="page"' : ''}>`
        + (p === 'landing' ? 'El proyecto' : 'Taller') + '</a>').join('')
    + '<span></span><a href="index.html">Índice</a>';
  document.body.appendChild(c);
})();

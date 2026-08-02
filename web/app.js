/* Taller Etapa 1 — frontend.
 *
 * No calcula nada del pipeline: arma formularios con lo que declara el backend, dispara ejecuciones y
 * dibuja resultados. Toda la ciencia ocurre del lado del servidor, llamando al paquete `tesis`.
 *
 * Modelo de navegación (lo importante):
 *   - Una RAMA es un camino de nodos, uno por etapa, desde los datos crudos.
 *   - `etapaVista` es la etapa que se está inspeccionando dentro de esa rama.
 *   - El panel de ejecución siempre apunta a la etapa SIGUIENTE a la vista. Si esa etapa ya existe en
 *     la rama, se avisa que ejecutar con otros parámetros abrirá una rama nueva.
 * Así inspeccionar y ramificar quedan separados, con la misma acción diciendo cuál de las dos hace.
 */

const S = {
  defs: [], cadena: [], nodos: [],
  rama: [],          // nodos de la rama actual, en orden de etapa
  etapaVista: null,  // índice dentro de S.cadena que se está inspeccionando (null = ninguna)
  sondeo: null,
};

const OFICIAL = {
  datos: { limpiar: true },
  ventaneo: { tamano_ventana: 50, paso: 1, deduplicar: true, umbral_dedup: 0.95 },
  features: {}, filtrado: {}, deteccion: {},
  eventos: { fraccion_candidatos: 0.01, max_ventanas_evento: 15 },
};

const $ = (s) => document.querySelector(s);
const api = async (ruta, op) => {
  const r = await fetch(ruta, op);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.status === 204 ? null : r.json();
};
const num = (v) => typeof v === 'number' ? v.toLocaleString('es') : v;

// ============================================================================ arranque
async function iniciar() {
  const def = await api('/api/etapas');
  S.defs = def.etapas; S.cadena = def.cadena;

  const est = await api('/api/estado');
  $('#sello').textContent = `tesis @ ${est.commit_tesis}`;
  if (!est.datos_listos) {
    $('#alerta-datos').innerHTML = `<div class="aviso" style="margin:16px 0">
      <strong>Faltan los datos base.</strong> Generalos una vez con
      <span class="mono">mise run datos</span> y recargá la página.</div>`;
  }

  await cargarNodos();
  nuevaRama();

  $('#btn-ejecutar').addEventListener('click', ejecutar);
  $('#btn-nueva').addEventListener('click', nuevaRama);
  $('#btn-restablecer').addEventListener('click', () => pintarFormulario(true));
  $('#btn-oficial').addEventListener('click', correrOficial);
}

async function cargarNodos() {
  S.nodos = (await api('/api/arbol')).nodos;
  pintarRamas();
}

// ============================================================================ ramas
/** Las hojas del árbol: cada una identifica una rama completa. */
function hojas() {
  const conHijos = new Set(S.nodos.map((n) => n.padre).filter(Boolean));
  return S.nodos.filter((n) => !conHijos.has(n.clave));
}

function cadenaDe(clave) {
  const cadena = [];
  let n = S.nodos.find((x) => x.clave === clave);
  while (n) { cadena.unshift(n); n = S.nodos.find((x) => x.clave === n.padre); }
  return cadena;
}

const esOficial = (cadena) => cadena.length === S.cadena.length &&
  cadena.every((n) => Object.entries(OFICIAL[n.etapa] || {})
    .every(([k, v]) => JSON.stringify(n.parametros[k]) === JSON.stringify(v)));

function pintarRamas() {
  const hs = hojas();
  $('#cuenta-ramas').textContent = `${hs.length} · ${S.nodos.length} nodos`;
  const cont = $('#ramas');
  if (!hs.length) {
    cont.innerHTML = '<p class="tenue" style="font-size:.82rem">Todavía no ejecutaste nada.</p>';
    return;
  }
  const actual = S.rama.length ? S.rama[S.rama.length - 1].clave : null;
  cont.innerHTML = hs.map((h) => {
    const cadena = cadenaDe(h.clave);
    const activa = cadena.some((n) => n.clave === actual) && cadena.length >= S.rama.length;
    const via = cadena.map((n) => etiquetaCorta(n)).join(' › ');
    return `<div class="rama ${activa ? 'activa' : ''}" data-clave="${h.clave}">
      <div style="min-width:0">
        <div class="titulo">${cadena.length}/${S.cadena.length} · ${h.etapa}
          ${esOficial(cadena) ? '<span class="oficial">★ oficial</span>' : ''}</div>
        <div class="via" title="${via}">${via}</div>
      </div>
      <button class="borrar" data-borrar="${cadena[0].clave === h.clave ? h.clave : h.clave}"
              title="Borrar esta rama">✕</button>
    </div>`;
  }).join('');

  cont.querySelectorAll('.rama').forEach((el) => el.addEventListener('click', (ev) => {
    if (ev.target.closest('.borrar')) return;
    cargarRama(el.dataset.clave);
  }));
  cont.querySelectorAll('.borrar').forEach((el) => el.addEventListener('click', async (ev) => {
    ev.stopPropagation();
    await borrarNodo(el.dataset.borrar);
  }));
}

const etiquetaCorta = (n) => {
  const p = n.parametros || {};
  return ({
    datos: () => p.limpiar ? 'limpio' : 'sin limpiar',
    ventaneo: () => `v${p.tamano_ventana}/p${p.paso}${p.deduplicar ? `·d${p.umbral_dedup}` : '·sin dedup'}`,
    features: () => `${p.rezagos_autocorr} rezagos`,
    filtrado: () => `corr ${p.umbral_correlacion}`,
    deteccion: () => `${(p.detectores || []).length} det`,
    eventos: () => `${(p.fraccion_candidatos * 100).toFixed(1)}%·máx${p.max_ventanas_evento || '∞'}`,
  }[n.etapa] || (() => n.etapa))();
};

async function borrarNodo(clave) {
  const cad = cadenaDe(clave);
  const cuantos = 1 + S.nodos.filter((n) => cadenaDe(n.clave).some((x) => x.clave === clave)
                                             && n.clave !== clave).length;
  if (!confirm(`Se van a borrar ${cuantos} nodo(s) y sus resultados en disco.\n` +
               `Rama: ${cad.map(etiquetaCorta).join(' › ')}\n\n¿Seguir?`)) return;
  const r = await api(`/api/nodo/${clave}`, { method: 'DELETE' });
  await cargarNodos();
  if (S.rama.some((n) => n.clave === clave)) nuevaRama();
  else pintarTodo();
  $('#estado-ejecucion').textContent =
    `Borrados ${r.borrados} nodos · ${(r.bytes_liberados / 1e6).toFixed(1)} MB liberados`;
}

function nuevaRama() {
  S.rama = []; S.etapaVista = null;
  pintarTodo();
}

function cargarRama(clave) {
  S.rama = cadenaDe(clave);
  S.etapaVista = S.rama.length - 1;
  pintarTodo();
  inspeccionar();
}

function pintarTodo() { pintarRamas(); pintarRecorrido(); pintarFormulario(true); }

// ============================================================================ recorrido
function pintarRecorrido() {
  const cont = $('#recorrido');
  cont.innerHTML = S.cadena.map((etapa, i) => {
    const nodo = S.rama[i];
    const def = S.defs.find((d) => d.nombre === etapa);
    let cls = '', detalle = 'pendiente';
    if (nodo) { cls = 'hecha'; detalle = etiquetaCorta(nodo); }
    if (i === S.etapaVista) cls += ' vista';
    if (i === indiceSiguiente()) { cls += ' siguiente'; detalle = nodo ? detalle : 'a ejecutar'; }
    const bloqueada = !nodo && i > indiceSiguiente();
    return `<button class="etapa-chip ${cls}" data-i="${i}" ${bloqueada ? 'disabled' : ''}>
      <span class="n">${i + 1}</span><span class="t">${def.titulo}</span>
      <span class="d">${detalle}</span></button>`;
  }).join('');
  cont.querySelectorAll('.etapa-chip').forEach((el) => el.addEventListener('click', () => {
    const i = Number(el.dataset.i);
    if (S.rama[i]) { S.etapaVista = i; pintarTodo(); inspeccionar(); }
  }));
}

/** Índice de la etapa que ejecutaría el formulario: la siguiente a la que se está viendo. */
function indiceSiguiente() {
  const base = S.etapaVista === null ? -1 : S.etapaVista;
  return Math.min(base + 1, S.cadena.length - 1);
}

// ============================================================================ formulario
function pintarFormulario(restablecer = false) {
  const i = indiceSiguiente();
  const yaHecha = S.etapaVista !== null && S.etapaVista >= S.cadena.length - 1;
  const def = S.defs.find((d) => d.nombre === S.cadena[i]);
  const panel = $('#panel-ejecutar');

  if (yaHecha) { panel.style.display = 'none'; return; }
  panel.style.display = 'block';

  $('#ejec-titulo').textContent = `${i + 1}. ${def.titulo}`;
  $('#ejec-desc').textContent = def.descripcion;

  const existente = S.rama[i];
  const modo = $('#ejec-modo');
  if (existente) {
    modo.className = 'chip oficial';
    modo.textContent = 'cambiar algo abre una rama nueva';
  } else if (S.etapaVista === null) {
    modo.className = 'chip pendiente';
    modo.textContent = 'rama nueva desde los datos crudos';
  } else {
    modo.className = 'chip corriendo';
    modo.textContent = 'continúa la rama actual';
  }

  const previos = restablecer && existente ? existente.parametros : null;
  $('#formulario').innerHTML = def.parametros.map((p) => {
    const id = `p_${p.nombre}`;
    const val = previos && previos[p.nombre] !== undefined ? previos[p.nombre] : p.defecto;
    if (p.tipo === 'booleano') {
      return `<div class="campo"><label class="interruptor">
        <input type="checkbox" id="${id}" ${val ? 'checked' : ''}> ${p.etiqueta}</label>
        ${p.ayuda ? `<div class="ayuda">${p.ayuda}</div>` : ''}</div>`;
    }
    if (p.tipo === 'multiple') {
      const ops = p.opciones || p.defecto || [];
      const marcadas = new Set(val || []);
      return `<div class="campo" style="grid-column:1/-1"><label>${p.etiqueta}</label>
        <div class="opciones">${ops.map((o) => `<label><input type="checkbox" name="${id}"
          value="${o}" ${marcadas.has(o) ? 'checked' : ''}> ${o}</label>`).join('')}</div>
        ${p.ayuda ? `<div class="ayuda">${p.ayuda}</div>` : ''}</div>`;
    }
    return `<div class="campo"><label for="${id}">${p.etiqueta}</label>
      <input type="number" id="${id}" value="${val}" step="${p.tipo === 'decimal' ? 'any' : '1'}"
       ${p.minimo != null ? `min="${p.minimo}"` : ''} ${p.maximo != null ? `max="${p.maximo}"` : ''}>
      ${p.ayuda ? `<div class="ayuda">${p.ayuda}</div>` : ''}</div>`;
  }).join('');
}

function leerFormulario() {
  const def = S.defs.find((d) => d.nombre === S.cadena[indiceSiguiente()]);
  const params = {};
  def.parametros.forEach((p) => {
    const id = `p_${p.nombre}`;
    if (p.tipo === 'booleano') params[p.nombre] = $(`#${id}`).checked;
    else if (p.tipo === 'multiple')
      params[p.nombre] = [...document.querySelectorAll(`input[name="${id}"]:checked`)].map((e) => e.value);
    else params[p.nombre] = Number($(`#${id}`).value);
  });
  return params;
}

// ============================================================================ ejecución
async function ejecutar() {
  const i = indiceSiguiente();
  const padre = S.etapaVista === null ? null : S.rama[S.etapaVista].clave;
  await lanzar(S.cadena[i], padre, leerFormulario());
}

async function lanzar(etapa, padre, parametros) {
  $('#btn-ejecutar').disabled = true;
  $('#estado-ejecucion').textContent = 'Encolando…';
  try {
    const r = await api('/api/ejecutar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ etapa, padre, parametros }),
    });
    if (r.reutilizado) {
      $('#estado-ejecucion').textContent = '✓ Ya estaba calculado — reutilizado del caché';
      await cargarNodos(); cargarRama(r.clave);
      $('#btn-ejecutar').disabled = false;
      return r.clave;
    }
    return await sondear(r.clave);
  } catch (e) {
    $('#estado-ejecucion').textContent = `Error: ${e.message}`;
    $('#btn-ejecutar').disabled = false;
    throw e;
  }
}

function sondear(clave) {
  return new Promise((resolver, rechazar) => {
    clearInterval(S.sondeo);
    const t0 = Date.now();
    S.sondeo = setInterval(async () => {
      const n = await api(`/api/nodo/${clave}`);
      $('#estado-ejecucion').textContent = `${n.estado}… ${((Date.now() - t0) / 1000).toFixed(0)}s`;
      if (n.estado !== 'listo' && n.estado !== 'error') return;
      clearInterval(S.sondeo);
      $('#btn-ejecutar').disabled = false;
      await cargarNodos();
      if (n.estado === 'error') {
        $('#estado-ejecucion').innerHTML = '<span style="color:var(--peligro)">Falló</span>';
        $('#panel-inspeccion').style.display = 'block';
        $('#insp-titulo').textContent = 'Error en la ejecución';
        $('#insp-resumen').innerHTML = '';
        $('#insp-visual').innerHTML =
          `<pre class="mono" style="white-space:pre-wrap;color:var(--peligro);font-size:.78rem">${n.error}</pre>`;
        return rechazar(new Error('falló la etapa'));
      }
      $('#estado-ejecucion').textContent = `✓ Listo en ${n.duracion_s}s`;
      cargarRama(clave);
      resolver(clave);
    }, 800);
  });
}

async function correrOficial() {
  $('#btn-oficial').disabled = true;
  nuevaRama();
  try {
    let padre = null;
    for (const etapa of S.cadena) {
      const def = S.defs.find((d) => d.nombre === etapa);
      const params = { ...Object.fromEntries(def.parametros.map((p) => [p.nombre, p.defecto])),
                       ...(OFICIAL[etapa] || {}) };
      $('#estado-ejecucion').textContent = `Ejecutando ${etapa}…`;
      padre = await lanzar(etapa, padre, params);
    }
    $('#estado-ejecucion').textContent = '✓ Configuración oficial completa';
  } catch { /* el error ya se muestra */ }
  $('#btn-oficial').disabled = false;
}

// ============================================================================ inspección
async function inspeccionar() {
  const nodo = S.rama[S.etapaVista];
  const panel = $('#panel-inspeccion');
  if (!nodo || nodo.estado !== 'listo') { panel.style.display = 'none'; return; }
  panel.style.display = 'block';

  const def = S.defs.find((d) => d.nombre === nodo.etapa);
  $('#insp-titulo').textContent = `${S.etapaVista + 1}. ${def.titulo}`;
  $('#insp-tiempo').textContent = `${nodo.duracion_s ?? 0}s`;
  $('#insp-clave').textContent = nodo.clave;
  $('#insp-params').textContent = Object.entries(nodo.parametros)
    .map(([k, v]) => `${k}=${Array.isArray(v) ? `[${v.length}]` : v}`).join('  ·  ');

  $('#insp-resumen').innerHTML = Object.entries(nodo.resumen || {})
    .filter(([, v]) => typeof v !== 'object' || Array.isArray(v))
    .map(([k, v]) => `<div class="celda"><div class="v">${Array.isArray(v) ? v.length : num(v === true ? 'sí' : v === false ? 'no' : v)}</div>
      <div class="r">${k.replace(/_/g, ' ')}</div></div>`).join('');

  const vis = $('#insp-visual');
  vis.innerHTML = '<p class="tenue" style="font-size:.85rem">Cargando datos…</p>';
  try {
    const d = await api(`/api/nodo/${nodo.clave}/datos`);
    vis.innerHTML = '';
    ({ serie: verSerie, ventanas: verVentanas, features: verFeatures,
       filtrado: verFiltrado, scores: verScores, eventos: verEventos }[d.tipo] || (() => {}))(d, nodo);
  } catch (e) {
    vis.innerHTML = `<p class="tenue" style="font-size:.85rem">Sin vista para esta etapa (${e.message})</p>`;
  }
}

// ---------------------------------------------------------------- vistas por etapa
const COLORES = ['#4ea8ff', '#7ef0c0', '#ffc86b', '#ff8a5b', '#c58cff'];

function lienzo(destino, alto = 200) {
  const c = document.createElement('canvas');
  const ancho = destino.clientWidth || 700;
  c.width = ancho * 2; c.height = alto * 2; c.style.height = `${alto}px`;
  destino.appendChild(c);
  const ctx = c.getContext('2d'); ctx.scale(2, 2);
  return { ctx, ancho, alto };
}

/** Dibuja N series superpuestas, cada una normalizada a su propio rango. */
function trazar(ctx, ancho, alto, series, nombres, { margen = 26 } = {}) {
  ctx.clearRect(0, 0, ancho, alto);
  series.forEach((serie, s) => {
    const limpios = serie.filter((v) => v != null);
    if (!limpios.length) return;
    const mn = Math.min(...limpios), mx = Math.max(...limpios), rango = (mx - mn) || 1;
    ctx.beginPath();
    let arrancado = false;
    serie.forEach((v, j) => {
      if (v == null) { arrancado = false; return; }
      const x = (j / Math.max(1, serie.length - 1)) * (ancho - margen * 1.4) + margen * .7;
      const y = alto - margen - ((v - mn) / rango) * (alto - margen * 1.9);
      arrancado ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      arrancado = true;
    });
    ctx.strokeStyle = COLORES[s % COLORES.length]; ctx.lineWidth = 1.6; ctx.stroke();
  });
  if (nombres) {
    ctx.font = '10px system-ui'; ctx.textAlign = 'left';
    nombres.forEach((n, s) => {
      ctx.fillStyle = COLORES[s % COLORES.length];
      ctx.fillText(n, 8 + s * 96, 12);
    });
  }
}

function verSerie(d) {
  const vis = $('#insp-visual');
  vis.innerHTML = `<div class="fila-sup"><h4 style="font-size:.92rem">Telemetría de una hoja</h4>
    <span class="esp"></span>
    <select id="sel-hoja">${d.hojas.map((h) =>
      `<option ${h === d.hoja ? 'selected' : ''}>${h}</option>`).join('')}</select></div>
    <div id="caja-serie"></div>
    <p class="tenue" style="font-size:.78rem;margin-top:8px">Cada señal está escalada a su propio rango
    para que se vean juntas. Una medición cada 10–11 s.</p>
    <h4 style="font-size:.88rem;margin:18px 0 6px">Filas por hoja</h4><div id="caja-hojas"></div>`;
  const dibujar = (datos) => {
    $('#caja-serie').innerHTML = '';
    const { ctx, ancho, alto } = lienzo($('#caja-serie'), 210);
    trazar(ctx, ancho, alto, datos.senales.map((_, i) => datos.valores.map((f) => f[i])), datos.senales);
  };
  dibujar(d);
  barras($('#caja-hojas'), d.por_hoja);
  $('#sel-hoja').addEventListener('change', async (e) => {
    const nodo = S.rama[S.etapaVista];
    dibujar(await api(`/api/nodo/${nodo.clave}/datos?hoja=${encodeURIComponent(e.target.value)}`));
  });
}

function verVentanas(d) {
  const vis = $('#insp-visual');
  vis.innerHTML = `<h4 style="font-size:.92rem;margin:0 0 4px">Ventanas de ejemplo</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:10px">Cuatro ventanas repartidas a lo largo
    del conjunto. Cada una son ${d.tamano} muestras (~${Math.round(d.tamano * 10.6 / 60)} min).</p>
    <div class="mini" id="caja-mini"></div>
    <h4 style="font-size:.88rem;margin:18px 0 6px">Ventanas por hoja</h4><div id="caja-hojas"></div>`;
  const cont = $('#caja-mini');
  d.ejemplos.forEach((ej) => {
    const caja = document.createElement('div');
    caja.className = 'caja';
    caja.innerHTML = `<h5>${ej.hoja} · desde ${ej.inicio}</h5>`;
    cont.appendChild(caja);
    const { ctx, ancho, alto } = lienzo(caja, 110);
    trazar(ctx, ancho, alto, d.senales.map((_, i) => ej.valores.map((f) => f[i])), null, { margen: 12 });
  });
  vis.insertAdjacentHTML('beforeend',
    `<p class="tenue" style="font-size:.78rem;margin-top:8px">${d.senales.join(' · ')}</p>`);
  barras($('#caja-hojas'), d.por_hoja);
}

function verFeatures(d) {
  $('#insp-visual').innerHTML = `<h4 style="font-size:.92rem">Catálogo calculado (${d.total})</h4>
    ${Object.entries(d.por_senal).map(([senal, fs]) => `
      <div style="margin-top:12px"><div class="mono tenue" style="font-size:.8rem;margin-bottom:6px">
        ${senal} <span style="color:var(--acento-2)">${fs.length}</span></div>
      <div class="pildoras">${fs.map((f) => `<span class="pildora">${f}</span>`).join('')}</div></div>`).join('')}`;
}

function verFiltrado(d) {
  $('#insp-visual').innerHTML = `
    <div class="rejilla c2">
      <div><h4 style="font-size:.9rem;color:var(--ok)">Conservadas (${d.conservadas.length})</h4>
        <div class="pildoras">${d.conservadas.map((f) =>
          `<span class="pildora">${f.replace('__', ' · ')}</span>`).join('')}</div></div>
      <div><h4 style="font-size:.9rem;color:var(--texto-2)">Descartadas (${d.descartadas.length})</h4>
        <div class="pildoras">${d.descartadas.map((f) =>
          `<span class="pildora baja">${f.replace('__', ' · ')}</span>`).join('')}</div></div>
    </div>
    <p class="tenue" style="font-size:.78rem;margin-top:12px">Se descartan las de baja variabilidad
    (no distinguen ventanas) y las redundantes (dicen lo mismo que otra).</p>`;
}

function verScores(d) {
  const vis = $('#insp-visual');
  vis.innerHTML = `<h4 style="font-size:.92rem;margin:0 0 4px">Distribución de puntajes</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:8px">Percentil 0 → 100. Cada curva está
    escalada a su propio máximo: <strong>las escalas de los detectores no son comparables entre
    sí</strong>.</p><div id="caja-perc"></div>
    <h4 style="font-size:.88rem;margin:18px 0 8px">Ventanas más extremas por detector</h4>
    <div class="mini">${d.detectores.map((det, i) => `
      <div class="caja"><h5 style="color:${COLORES[i % 5]}">${det}</h5>
      <table style="font-size:.76rem"><tbody>${d.top[det].slice(0, 6).map((t) =>
        `<tr><td>${t.hoja}</td><td class="num">${t.inicio}</td>
         <td class="num" style="color:var(--acento-2)">${t.score.toFixed(2)}</td></tr>`).join('')}
      </tbody></table></div>`).join('')}</div>`;
  const { ctx, ancho, alto } = lienzo($('#caja-perc'), 200);
  trazar(ctx, ancho, alto, d.detectores.map((c) => d.percentiles[c]), d.detectores);
}

function verEventos(d) {
  const cols = ['event_id', 'SheetName', 'start', 'end', 'n_ventanas', 'n_detectores', 'features_top']
    .filter((c) => d.columnas.includes(c));
  const filas = [...d.filas].sort((a, b) => b.n_detectores - a.n_detectores || b.n_ventanas - a.n_ventanas);
  $('#insp-visual').innerHTML = `
    <div class="fila-sup"><h4 style="font-size:.92rem">Eventos candidatos (${filas.length})</h4>
      <span class="esp"></span>
      <span class="tenue" style="font-size:.78rem">clic en una fila para ver sus señales</span></div>
    <div class="tabla-scroll"><table><thead><tr>${cols.map((c) =>
      `<th>${({ n_detectores: 'prioridad', n_ventanas: 'ventanas', SheetName: 'hoja',
                event_id: 'id', start: 'desde', end: 'hasta',
                features_top: 'por qué' })[c] || c}</th>`).join('')}</tr></thead>
    <tbody>${filas.map((f) => `<tr data-ev="${f.event_id}" style="cursor:pointer">${cols.map((c) => {
      const v = f[c];
      if (c === 'n_detectores') return `<td class="num"><strong style="color:${v >= 4 ? 'var(--acento-2)' : 'var(--texto-2)'}">${v}/5</strong></td>`;
      if (c === 'features_top') return `<td class="mono" style="font-size:.71rem;color:var(--texto-2)">${(v || '').slice(0, 62)}</td>`;
      return typeof v === 'number' ? `<td class="num">${v}</td>` : `<td>${v}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div>
    <div id="detalle-evento" style="margin-top:16px"></div>`;

  document.querySelectorAll('#insp-visual tr[data-ev]').forEach((tr) =>
    tr.addEventListener('click', () => verEvento(Number(tr.dataset.ev))));
}

async function verEvento(id) {
  const nodo = S.rama[S.etapaVista];
  const cont = $('#detalle-evento');
  cont.innerHTML = '<p class="tenue" style="font-size:.84rem">Cargando…</p>';
  try {
    const d = await api(`/api/nodo/${nodo.clave}/evento/${id}`);
    const ev = d.evento;
    cont.innerHTML = `<div class="caja" style="background:var(--fondo-2);border:1px solid var(--borde);
        border-radius:10px;padding:14px">
      <div class="fila-sup"><h4 style="font-size:.9rem">Evento ${id} · ${ev.SheetName}</h4>
        <span class="chip ${ev.n_detectores >= 4 ? 'listo' : 'pendiente'}">${ev.n_detectores}/5</span>
        <span class="esp"></span>
        <span class="mono tenue" style="font-size:.76rem">pasos ${ev.start}–${ev.end} ·
          ${ev.n_ventanas} ventanas</span></div>
      <div id="caja-ev"></div>
      <p class="mono tenue" style="font-size:.74rem;margin-top:8px">${ev.features_top || ''}</p></div>`;
    const { ctx, ancho, alto } = lienzo($('#caja-ev'), 190);
    trazar(ctx, ancho, alto, d.senales.map((_, i) => d.valores.map((f) => f[i])), d.senales);
  } catch (e) {
    cont.innerHTML = `<p class="tenue" style="font-size:.84rem">No se pudo cargar: ${e.message}</p>`;
  }
}

function barras(destino, mapa) {
  const { ctx, ancho, alto } = lienzo(destino, 150);
  const ent = Object.entries(mapa);
  if (!ent.length) return;
  const max = Math.max(...ent.map(([, v]) => v));
  const w = ancho / ent.length;
  ent.forEach(([k, v], i) => {
    const h = (v / max) * (alto - 40);
    const g = ctx.createLinearGradient(0, alto - h - 22, 0, alto - 22);
    g.addColorStop(0, '#7ef0c0'); g.addColorStop(1, '#4ea8ff');
    ctx.fillStyle = g; ctx.fillRect(i * w + 2, alto - h - 22, Math.max(2, w - 4), h);
    ctx.save(); ctx.translate(i * w + w / 2, alto - 14); ctx.rotate(-Math.PI / 9);
    ctx.fillStyle = '#93a4c0'; ctx.font = '9px system-ui'; ctx.textAlign = 'right';
    ctx.fillText(k.slice(0, 13), 0, 0); ctx.restore();
  });
}

iniciar().catch((e) => document.querySelector('.envoltorio').insertAdjacentHTML('afterbegin',
  `<div class="aviso" style="margin:20px 0"><strong>No se pudo iniciar:</strong> ${e.message}</div>`));

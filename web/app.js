/* Taller Etapa 1 — frontend.
 *
 * No calcula nada del pipeline: dibuja el árbol de ejecuciones, arma formularios con lo que declara el
 * backend y muestra resultados. Toda la ciencia ocurre en el servidor, llamando al paquete `tesis`.
 *
 * Modelo de la interfaz:
 *   - El MAPA es el árbol real de nodos, dibujado. Las ramas se ven como bifurcaciones.
 *   - Al seleccionar un nodo se abre la vista de esa FASE: qué entró, qué salió, con qué parámetros y
 *     los datos que produjo.
 *   - Desde la fase hay dos acciones explícitas: continuar al paso siguiente, o volver a ejecutar
 *     ESTE paso con otros valores (lo que abre una rama). Nunca queda implícito cuál de las dos pasa.
 */

const S = {
  defs: [], cadena: [], nodos: [],
  sel: null,          // clave del nodo seleccionado (null = todavía nada, arranca desde cero)
  form: null,         // {etapa, padre, modo} cuando el formulario está abierto
  sondeo: null,
  vista: 'paso',      // 'paso' | 'analisis' — qué pestaña de la fase se está mirando
  detector: null,     // método elegido para la dispersión del análisis
  // Configuración de referencia de la tesis y segundos entre mediciones: los sirve el backend desde
  // `backend/ajustes.py` (ajustable por .env), para que no estén duplicados acá.
  oficial: {},
  muestreo: 10.6,
};

/* Los gráficos van en <canvas>, que se pinta a mano y no hereda nada de CSS. Los colores se leen de
 * las variables de `estilos.css` para no tener una segunda paleta acá que se desincronice con el
 * tema. Se leen en cada dibujo, no una vez al arrancar, porque cambian al cambiar de tema. */

const $ = (s) => document.querySelector(s);
const api = async (ruta, op) => {
  const r = await fetch(ruta, op);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
};
const miles = (v) => typeof v === 'number' ? v.toLocaleString('es') : v;

// ============================================================================ arranque
async function iniciar() {
  const def = await api('/api/etapas');
  S.defs = def.etapas; S.cadena = def.cadena;

  const est = await api('/api/estado');
  S.oficial = est.config_tesis || {};
  S.muestreo = est.muestreo_segundos || 10.6;
  $('#sello').textContent = `tesis @ ${est.commit_tesis}`;
  $('#sello').title = `Paquete de la tesis instalado desde ${est.ruta_tesis}`;
  if (!est.datos_listos) {
    $('#alerta-datos').innerHTML = `<div class="aviso" style="margin:16px 0">
      <strong>Faltan los datos base.</strong> Generalos una vez con
      <span class="mono">mise run datos</span> y recargá la página.</div>`;
  }

  await recargar();

  // Compatibilidad con los enlaces de la pantalla de análisis, que ahora es una pestaña de acá.
  const url = new URLSearchParams(location.search);
  const pedido = url.get('nodo');
  if (pedido && S.nodos.some((n) => n.clave === pedido)) {
    S.sel = pedido;
    if (url.get('vista') === 'analisis') S.vista = 'analisis';
    pintar();
    cargarVisual();
  }
  $('#btn-nueva').addEventListener('click', () => { S.sel = null; pintar(); abrirForm('datos', null, 'nueva'); });
  $('#btn-oficial').addEventListener('click', correrOficial);
  $('#btn-cancelar').addEventListener('click', () => { S.form = null; pintar(); });
  $('#btn-ejecutar').addEventListener('click', ejecutarForm);
  $('#btn-borrar').addEventListener('click', borrarSeleccion);
  addEventListener('resize', dibujarMapa);
}

async function recargar() {
  S.nodos = (await api('/api/arbol')).nodos;
  if (S.sel && !S.nodos.find((n) => n.clave === S.sel)) S.sel = null;
  pintar();
}

function pintar() { dibujarMapa(); pintarFase(); pintarForm(); }

// ============================================================================ mapa
const hijosDe = (clave) => S.nodos.filter((n) => n.padre === clave);
const nodoDe = (clave) => S.nodos.find((n) => n.clave === clave);

function cadenaDe(clave) {
  const c = []; let n = nodoDe(clave);
  while (n) { c.unshift(n); n = nodoDe(n.padre); }
  return c;
}

const esOficial = (n) => Object.entries(S.oficial[n.etapa] || {})
  .every(([k, v]) => JSON.stringify(n.parametros[k]) === JSON.stringify(v));
const ramaOficial = (clave) => cadenaDe(clave).every(esOficial);

/** Ubica cada nodo: columna = etapa, fila = orden en el árbol (hijos consecutivos, padres centrados). */
function ubicar() {
  const pos = new Map();
  let fila = 0;
  const recorrer = (n) => {
    const hijos = hijosDe(n.clave);
    if (!hijos.length) { pos.set(n.clave, fila++); return pos.get(n.clave); }
    const filas = hijos.map(recorrer);
    const f = (Math.min(...filas) + Math.max(...filas)) / 2;
    pos.set(n.clave, f);
    return f;
  };
  S.nodos.filter((n) => !n.padre).forEach(recorrer);
  return { pos, filas: Math.max(1, fila) };
}

function dibujarMapa() {
  const svg = $('#mapa');
  const COL = Math.max(150, Math.min(210, ($('#mapa-caja').clientWidth - 40) / 6));
  const FILA = 62, MT = 34, ML = 30;
  const { pos, filas } = ubicar();
  const alto = MT + filas * FILA + 14;
  const ancho = ML + S.cadena.length * COL;
  svg.setAttribute('height', alto);
  svg.setAttribute('width', ancho);
  svg.setAttribute('viewBox', `0 0 ${ancho} ${alto}`);

  const x = (etapa) => ML + S.cadena.indexOf(etapa) * COL + COL / 2 - 30;
  const y = (clave) => MT + pos.get(clave) * FILA;

  const partes = [];
  // encabezados de columna
  S.cadena.forEach((e, i) => {
    const def = S.defs.find((d) => d.nombre === e);
    const cx = ML + i * COL + COL / 2 - 30;
    partes.push(`<text class="col-t" x="${cx}" y="14" text-anchor="middle">${i + 1}. ${def.titulo}</text>`);
    partes.push(`<line class="col-l" x1="${cx}" y1="22" x2="${cx}" y2="${alto - 6}"/>`);
  });

  const enRama = new Set(S.sel ? cadenaDe(S.sel).map((n) => n.clave) : []);

  // aristas
  S.nodos.filter((n) => n.padre).forEach((n) => {
    const x1 = x(nodoDe(n.padre).etapa), y1 = y(n.padre), x2 = x(n.etapa), y2 = y(n.clave);
    const m = (x1 + x2) / 2;
    const viva = enRama.has(n.clave) && enRama.has(n.padre);
    partes.push(`<path class="arista ${viva ? 'viva' : ''}"
      d="M ${x1 + 13} ${y1} C ${m} ${y1}, ${m} ${y2}, ${x2 - 13} ${y2}"/>`);
  });

  // nodos
  S.nodos.forEach((n) => {
    const cx = x(n.etapa), cy = y(n.clave);
    const sel = n.clave === S.sel ? 'sel' : '';
    partes.push(`<g class="nodo-g" data-clave="${n.clave}">
      <circle class="nodo-c ${n.estado} ${sel}" cx="${cx}" cy="${cy}" r="13"/>
      ${ramaOficial(n.clave) && n.etapa === 'eventos' ? `<text class="estrella" x="${cx + 15}" y="${cy - 9}">★</text>` : ''}
      <text class="nodo-t" x="${cx}" y="${cy + 3.5}" text-anchor="middle">${S.cadena.indexOf(n.etapa) + 1}</text>
      <text class="nodo-s" x="${cx}" y="${cy + 27}" text-anchor="middle">${etiqueta(n)}</text>
      <title>${n.etapa} · ${etiqueta(n)} · ${n.estado}${n.duracion_s ? ` · ${n.duracion_s}s` : ''}</title>
    </g>`);
  });

  // nodo fantasma: dónde caería el próximo paso
  const sig = etapaSiguiente();
  if (sig) {
    const cy = S.sel ? y(S.sel) : MT;
    partes.push(`<circle class="fantasma" cx="${x(sig)}" cy="${cy}" r="13"/>
      <text class="nodo-t" x="${x(sig)}" y="${cy + 4}" text-anchor="middle"
        style="fill:var(--acento)">+</text>`);
    if (S.sel) {
      const m = (x(nodoDe(S.sel).etapa) + x(sig)) / 2;
      partes.push(`<path class="arista" style="stroke-dasharray:4 4;stroke:var(--acento)"
        d="M ${x(nodoDe(S.sel).etapa) + 13} ${cy} C ${m} ${cy}, ${m} ${cy}, ${x(sig) - 13} ${cy}"/>`);
    }
  }

  svg.innerHTML = partes.join('');
  svg.querySelectorAll('.nodo-g').forEach((g) => g.addEventListener('click', () => {
    S.sel = g.dataset.clave; S.form = null; S.vista = 'paso'; S.detector = null;
    pintar(); cargarVisual();
  }));

  $('#cuenta').textContent = `${S.nodos.length} pasos · ${hojas().length} ramas`;
  $('#pista-mapa').textContent = S.nodos.length
    ? 'Clic en un círculo para ver ese paso en detalle. El círculo punteado es dónde caería el próximo.'
    : 'Todavía no hay nada. Empezá de cero o corré la configuración de la tesis.';
}

const hojas = () => {
  const padres = new Set(S.nodos.map((n) => n.padre).filter(Boolean));
  return S.nodos.filter((n) => !padres.has(n.clave));
};

function etiqueta(n) {
  const p = n.parametros || {};
  return ({
    datos: () => p.limpiar ? 'limpio' : 'sin limpiar',
    ventaneo: () => `${p.tamano_ventana}/${p.paso}${p.deduplicar ? ` · ${p.umbral_dedup}` : ' · sin dedup'}`,
    features: () => `${p.rezagos_autocorr} rezagos`,
    filtrado: () => `corr ${p.umbral_correlacion}`,
    deteccion: () => `${(p.detectores || []).length} métodos`,
    eventos: () => `${(p.fraccion_candidatos * 100).toFixed(1)}% · tope ${p.max_ventanas_evento || '∞'}`,
  }[n.etapa] || (() => n.etapa))();
}

function etapaSiguiente() {
  if (!S.sel) return S.cadena[0];
  const i = S.cadena.indexOf(nodoDe(S.sel).etapa);
  return i + 1 < S.cadena.length ? S.cadena[i + 1] : null;
}

// ============================================================================ fase
/** Qué entra y qué sale de cada etapa, en números, para la tira de flujo. */
function flujoDe(nodo) {
  const r = nodo.resumen || {};
  return ({
    datos: () => [`${miles(r.filas_entrada)} mediciones`,
                  `${miles(r.filas_salida)} mediciones · ${r.hojas} hojas`],
    ventaneo: () => [`${miles(r.ventanas_generadas)} tramos generados`,
                     `${miles(r.ventanas_conservadas)} tramos` +
                     (r.eliminadas_por_dedup ? ` (−${r.reduccion_pct} %)` : '')],
    features: () => [`${miles(r.filas)} tramos`, `${miles(r.filas)} × ${r.features} características`],
    filtrado: () => [`${r.features_entrada} características`, `${r.features_salida} características`],
    deteccion: () => [`${miles(r.ventanas_puntuadas)} tramos`,
                      `${miles(r.ventanas_puntuadas)} × ${(r.detectores || []).length} puntajes`],
    eventos: () => [`${miles(r.ventanas_candidatas)} tramos sospechosos`, `${r.eventos} eventos`],
  }[nodo.etapa] || (() => ['—', '—']))();
}

function pintarFase() {
  const panel = $('#panel-fase');
  if (!S.sel) {
    panel.style.display = 'block';
    $('#fase-num').textContent = '0';
    $('#fase-num').className = 'num-fase pendiente';
    $('#fase-titulo').textContent = 'Sin ningún paso seleccionado';
    $('#fase-estado').textContent = '';
    $('#fase-desc').textContent = S.nodos.length
      ? 'Elegí un círculo del mapa para ver qué produjo ese paso, o empezá una rama nueva desde cero.'
      : 'El pipeline tiene 6 pasos. Arrancá por el primero, o corré de una la configuración con la que la tesis reporta sus resultados.';
    ['#fase-flujo', '#fase-params', '#fase-resumen', '#fase-visual'].forEach((s) => $(s).innerHTML = '');
    $('#btn-borrar').style.display = 'none';
    $('#fase-acciones').innerHTML = S.nodos.length ? '' :
      `<button class="boton primario" onclick="document.getElementById('btn-oficial').click()">★ Correr la configuración de la tesis</button>
       <button class="boton" onclick="document.getElementById('btn-nueva').click()">Configurar el paso 1 a mano</button>`;
    return;
  }

  const n = nodoDe(S.sel);
  const i = S.cadena.indexOf(n.etapa);
  const def = S.defs.find((d) => d.nombre === n.etapa);

  $('#fase-num').textContent = i + 1;
  $('#fase-num').className = 'num-fase';
  $('#fase-titulo').textContent = def.titulo;
  $('#fase-estado').className = `chip ${n.estado}`;
  $('#fase-estado').textContent = n.estado === 'listo'
    ? `paso ${i + 1} de 6 · ${n.duracion_s ?? 0}s` : n.estado;
  $('#fase-desc').textContent = def.descripcion;
  $('#btn-borrar').style.display = 'inline-flex';

  if (n.estado === 'listo') {
    const [entra, sale] = flujoDe(n);
    $('#fase-flujo').innerHTML = `
      <div class="caja-f"><div class="et">entra</div><div class="vl">${entra}</div></div>
      <span class="fl">→</span>
      <div class="caja-f sale"><div class="et">sale</div><div class="vl">${sale}</div></div>`;
  } else $('#fase-flujo').innerHTML = '';

  $('#fase-params').innerHTML = def.parametros.map((p) => {
    const v = n.parametros[p.nombre];
    return `<span class="par" title="${p.ayuda.slice(0, 180)}">${p.etiqueta}
      <b>${Array.isArray(v) ? `${v.length}` : (v === true ? 'sí' : v === false ? 'no' : v)}</b></span>`;
  }).join('');

  $('#fase-resumen').innerHTML = Object.entries(n.resumen || {})
    .filter(([, v]) => typeof v !== 'object' || Array.isArray(v))
    .map(([k, v]) => `<div class="celda"><div class="v">${Array.isArray(v) ? v.length
      : miles(v === true ? 'sí' : v === false ? 'no' : v)}</div>
      <div class="r">${k.replace(/_/g, ' ')}</div></div>`).join('');

  if (n.estado === 'error') {
    $('#fase-visual').innerHTML =
      `<pre class="mono" style="white-space:pre-wrap;color:var(--peligro);font-size:.78rem">${n.error}</pre>`;
  }

  // acciones: las dos rutas posibles, dichas con todas las letras
  const sig = etapaSiguiente();
  const defSig = sig && S.defs.find((d) => d.nombre === sig);
  const yaHecho = sig && hijosDe(S.sel).length;
  // El análisis es una pestaña de esta misma vista, no otra pantalla: el nodo ya está elegido
  // sobre el mapa, que es donde una rama se ve como lo que es —una bifurcación con su historia—
  // y no como una línea de texto en un desplegable.
  const analizable = n.estado === 'listo' && ['deteccion', 'eventos'].includes(n.etapa);
  $('#fase-acciones').innerHTML = `
    ${sig ? `<button class="boton primario" id="a-seguir">Paso ${i + 2}: ${defSig.titulo} →</button>` : ''}
    <button class="boton" id="a-ramificar">Repetir este paso con otros valores</button>
    ${analizable && S.vista !== 'analisis'
        ? '<button class="boton" id="a-analizar">Analizar esta rama →</button>' : ''}
    <span class="tenue" style="font-size:.82rem">
      ${sig ? (yaHecho ? 'Ya hay pasos más adelante; si cambiás algo, se abre una rama.'
                       : 'Continúa esta rama.') : 'Este es el último paso del pipeline.'}
    </span>`;
  if (sig) $('#a-seguir').addEventListener('click', () => abrirForm(sig, S.sel, 'seguir'));
  $('#a-ramificar').addEventListener('click', () => abrirForm(n.etapa, n.padre, 'rama'));
  if ($('#a-analizar')) $('#a-analizar').addEventListener('click', () => verPestana('analisis'));
  pintarPestanas(analizable);
}

async function borrarSeleccion() {
  const n = nodoDe(S.sel);
  const cuantos = 1 + S.nodos.filter((x) => cadenaDe(x.clave).some((y) => y.clave === S.sel)
                                            && x.clave !== S.sel).length;
  if (!confirm(`Se borran ${cuantos} paso(s) desde acá en adelante, con sus resultados en disco.\n` +
               `¿Seguir?`)) return;
  const r = await api(`/api/nodo/${S.sel}`, { method: 'DELETE' });
  S.sel = n.padre;
  await recargar();
  if (S.sel) cargarVisual();
  $('#estado-ejecucion').textContent =
    `Borrados ${r.borrados} pasos · ${(r.bytes_liberados / 1e6).toFixed(1)} MB liberados`;
}

// ============================================================================ formulario
function abrirForm(etapa, padre, modo) {
  S.form = { etapa, padre, modo };
  pintarForm();
  $('#panel-form').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

function pintarForm() {
  const panel = $('#panel-form');
  if (!S.form) { panel.classList.remove('abierto'); return; }
  panel.classList.add('abierto');

  const { etapa, padre, modo } = S.form;
  const def = S.defs.find((d) => d.nombre === etapa);
  const i = S.cadena.indexOf(etapa);
  $('#form-titulo').textContent = `Paso ${i + 1}: ${def.titulo}`;
  $('#form-desc').textContent = def.descripcion;

  const modos = {
    nueva: ['chip pendiente', 'arranca una rama desde cero'],
    seguir: ['chip corriendo', 'continúa la rama actual'],
    rama: ['chip oficial', 'si cambiás algo, se abre una rama nueva'],
  }[modo];
  $('#form-modo').className = modos[0];
  $('#form-modo').textContent = modos[1];

  // Si estamos repitiendo un paso, precargar sus valores para que se vea qué se está cambiando.
  const base = modo === 'rama' ? nodoDe(S.sel).parametros : null;
  $('#formulario').innerHTML = def.parametros.map((p) => {
    const id = `p_${p.nombre}`;
    const val = base && base[p.nombre] !== undefined ? base[p.nombre] : p.defecto;
    if (p.tipo === 'booleano') {
      return `<div class="campo" style="grid-column:1/-1"><label class="interruptor">
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

function leerForm() {
  const def = S.defs.find((d) => d.nombre === S.form.etapa);
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

const ejecutarForm = () => lanzar(S.form.etapa, S.form.padre, leerForm());

// ============================================================================ ejecución
async function lanzar(etapa, padre, parametros) {
  $('#btn-ejecutar').disabled = true;
  $('#estado-ejecucion').textContent = 'Encolando…';
  try {
    const r = await api('/api/ejecutar', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ etapa, padre, parametros }),
    });
    if (r.reutilizado) {
      $('#estado-ejecucion').textContent = '✓ Ya estaba calculado — se reutilizó';
      S.sel = r.clave; S.form = null;
      await recargar(); cargarVisual();
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
  return new Promise((ok, mal) => {
    clearInterval(S.sondeo);
    const t0 = Date.now();
    S.sondeo = setInterval(async () => {
      const n = await api(`/api/nodo/${clave}`);
      $('#estado-ejecucion').textContent = `${n.estado}… ${((Date.now() - t0) / 1000).toFixed(0)}s`;
      S.sel = clave;
      await recargar();
      if (n.estado !== 'listo' && n.estado !== 'error') return;
      clearInterval(S.sondeo);
      $('#btn-ejecutar').disabled = false;
      S.form = null;
      await recargar();
      if (n.estado === 'error') {
        $('#estado-ejecucion').innerHTML = '<span style="color:var(--peligro)">Falló</span>';
        return mal(new Error('falló'));
      }
      $('#estado-ejecucion').textContent = `✓ Listo en ${n.duracion_s}s`;
      cargarVisual(); ok(clave);
    }, 800);
  });
}

async function correrOficial() {
  $('#btn-oficial').disabled = true;
  S.sel = null; S.form = null; pintar();
  try {
    let padre = null;
    for (const etapa of S.cadena) {
      const def = S.defs.find((d) => d.nombre === etapa);
      const params = { ...Object.fromEntries(def.parametros.map((p) => [p.nombre, p.defecto])),
                       ...(S.oficial[etapa] || {}) };
      $('#estado-ejecucion').textContent = `Ejecutando ${etapa}…`;
      padre = await lanzar(etapa, padre, params);
    }
    $('#estado-ejecucion').textContent = '✓ Configuración de la tesis completa';
  } catch { /* ya se muestra */ }
  $('#btn-oficial').disabled = false;
}

// ============================================================================ visualizaciones
/** Las dos pestañas de la fase. La de análisis solo existe donde hay puntajes. */
function pintarPestanas(analizable) {
  const cont = $('#fase-pestanas');
  if (!analizable) {
    cont.hidden = true;
    cont.innerHTML = '';
    S.vista = 'paso';
    return;
  }
  cont.hidden = false;
  const tabs = [['paso', 'Este paso'], ['analisis', 'Análisis de la rama']];
  cont.innerHTML = tabs.map(([id, t]) =>
    `<button role="tab" data-vista="${id}" aria-selected="${S.vista === id}">${t}</button>`).join('');
  cont.querySelectorAll('button').forEach((b) =>
    b.addEventListener('click', () => verPestana(b.dataset.vista)));
}

function verPestana(vista) {
  if (S.vista === vista) return;
  S.vista = vista;
  S.detector = null;
  const n = nodoDe(S.sel);
  pintarPestanas(n && n.estado === 'listo' && ['deteccion', 'eventos'].includes(n.etapa));
  pintarFase();
  cargarVisual();
}

async function cargarVisual() {
  if (!S.sel) return;
  const n = nodoDe(S.sel);
  const vis = $('#fase-visual');
  if (!n || n.estado !== 'listo') return;
  Grafico.limpiar(vis);   // si no, quedan ResizeObservers observando nodos ya desprendidos
  vis.innerHTML = '<p class="tenue" style="font-size:.85rem">Cargando datos…</p>';
  try {
    if (S.vista === 'analisis') {
      const url = `/api/nodo/${n.clave}/analisis` + (S.detector ? `?detector=${encodeURIComponent(S.detector)}` : '');
      const d = await api(url);
      vis.innerHTML = '';
      Analisis.pintar(vis, d, (det) => { S.detector = det; cargarVisual(); });
      return;
    }
    const d = await api(`/api/nodo/${n.clave}/datos`);
    vis.innerHTML = '';
    ({ serie: verSerie, ventanas: verVentanas, features: verFeatures, filtrado: verFiltrado,
       scores: verScores, eventos: verEventos }[d.tipo] || (() => {}))(d);
  } catch (e) {
    vis.innerHTML = `<p class="tenue" style="font-size:.85rem">Sin vista para este paso (${e.message})</p>`;
  }
}

function verSerie(d) {
  $('#fase-visual').innerHTML = `<div class="fila-sup"><h4 style="font-size:.92rem">Telemetría de una hoja</h4>
    <span class="esp"></span><select id="sel-hoja">${d.hojas.map((h) =>
      `<option ${h === d.hoja ? 'selected' : ''}>${h}</option>`).join('')}</select></div>
    <div id="caja-serie"></div>
    <p class="tenue" style="font-size:.78rem;margin-top:8px">Un panel por señal, cada uno con su propia
    escala y su unidad, y el eje horizontal compartido. Antes iban las tres encimadas y escaladas cada
    una a su rango: se comparaban las formas, pero las alturas no querían decir nada y no había forma
    de leer un valor. Pasá el puntero para ver los tres valores a la vez, y usá la barra de abajo o la
    lupa de la esquina para acercarte a un tramo.</p>
    <h4 style="font-size:.88rem;margin:18px 0 6px">Mediciones por hoja</h4><div id="caja-hojas"></div>`;
  const dibujar = (dd) => {
    const caja = $('#caja-serie');
    Grafico.limpiar(caja);
    caja.innerHTML = '';
    Grafico.lineas(caja, {
      titulo: `${dd.hoja} · ${dd.valores.length} mediciones`,
      paneles: dd.senales.map((s, i) => ({ nombre: s, valores: dd.valores.map((f) => f[i]) })),
      xNombre: 'medición',
      sustantivo: 'mediciones',
    });
  };
  dibujar(d);
  Grafico.barras($('#caja-hojas'), {
    datos: Object.entries(d.por_hoja).map(([etiqueta, valor]) => ({ etiqueta, valor })),
    nota: 'Las 20 hojas con más mediciones.',
  });
  $('#sel-hoja').addEventListener('change', async (e) =>
    dibujar(await api(`/api/nodo/${S.sel}/datos?hoja=${encodeURIComponent(e.target.value)}`)));
}

function verVentanas(d) {
  $('#fase-visual').innerHTML = `<h4 style="font-size:.92rem;margin:0 0 4px">Cómo quedó un tramo</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:10px">Cuatro tramos tomados de distintas
    partes del conjunto. Cada uno son ${d.tamano} mediciones consecutivas
    (~${Math.round(d.tamano * S.muestreo / 60)} min) y es la unidad que los detectores van a puntuar.
    Pasá el puntero por encima para ver los valores.</p>
    <div class="mini" id="caja-mini"></div>
    <h4 style="font-size:.88rem;margin:18px 0 6px">Tramos por hoja</h4><div id="caja-hojas"></div>`;
  d.ejemplos.forEach((ej) => {
    const caja = document.createElement('div');
    caja.className = 'caja';
    const t = document.createElement('h5');
    t.textContent = `${ej.hoja} · desde la medición ${ej.inicio}`;
    caja.appendChild(t);
    $('#caja-mini').appendChild(caja);
    Grafico.lineas(caja, {
      compacto: true,
      altoPanel: 52,
      titulo: `${ej.hoja} · desde la medición ${ej.inicio}`,
      xNombre: 'posición',
      sustantivo: 'mediciones del tramo',
      paneles: d.senales.map((s, i) => ({ nombre: s, valores: ej.valores.map((f) => f[i]) })),
    });
  });
  Grafico.barras($('#caja-hojas'), {
    datos: Object.entries(d.por_hoja).map(([etiqueta, valor]) => ({ etiqueta, valor })),
    nota: 'Las 20 hojas con más tramos.',
  });
}

function verFeatures(d) {
  $('#fase-visual').innerHTML = `<h4 style="font-size:.92rem">Lo que se calculó para cada tramo
    (${d.total} números)</h4>
    <p class="tenue" style="font-size:.8rem">Las mismas ${Object.values(d.por_senal)[0]?.length ?? 0}
    medidas se calculan por separado para cada una de las tres señales.</p>
    ${Object.entries(d.por_senal).map(([senal, fs]) => `
      <div style="margin-top:12px"><div class="mono tenue" style="font-size:.8rem;margin-bottom:6px">
        ${senal} <span style="color:var(--acento-2)">${fs.length}</span></div>
      <div class="pildoras">${fs.map((f) => `<span class="pildora">${f}</span>`).join('')}</div></div>`).join('')}
    <h4 style="font-size:.88rem;margin:20px 0 4px">Y cómo se reparten esos números</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:6px">Cada caja abarca la mitad central de
    los tramos, y la línea de adentro es la mediana. <strong>El eje está en desvíos estándar</strong>,
    porque en sus unidades originales no se podrían poner juntas: una está en volts, otra en
    miliamperios y otra es una energía de seis cifras. Así el eje quiere decir una sola cosa para las
    ${d.total} y lo que se compara es la forma: las de cola larga son las que van a servir para
    encontrar tramos raros.</p>
    <div id="caja-feats"></div>`;
  cajasDeFeatures($('#caja-feats'), d.cajas);
}

/** Caja y bigotes de las 72 características, coloreadas por señal. */
function cajasDeFeatures(destino, cajas) {
  const senal = (n) => (n.includes('__') ? n.split('__')[0] : 'otras');
  const senales = [...new Set(cajas.map((c) => senal(c.nombre)))];
  const corto = (n) => n.replace('__', ' · ');
  const alto = cajas.length * 15 + 70;
  Grafico.medida(destino, {
    titulo: 'Distribución de cada característica',
    alto,
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 200, right: 26, top: 26, bottom: 34 },
      tooltip: Object.assign({}, c.tooltip, {
        trigger: 'item',
        formatter: (p) => {
          const k = cajas[p.dataIndex];
          return `<b>${corto(k.nombre)}</b><br>` +
            `<span style="color:${c.tenue}">mediana ${k.caja[2]} · cuartiles ${k.caja[1]} a ${k.caja[3]}` +
            `<br>${k.atipicos} tramos fuera de los bigotes</span>`;
        },
      }),
      xAxis: Object.assign({}, c.eje, { type: 'value', name: 'desvíos estándar',
        nameLocation: 'middle', nameGap: 22, nameTextStyle: { color: c.tenue } }),
      yAxis: Object.assign({}, c.eje, { type: 'category', data: cajas.map((k) => corto(k.nombre)),
        inverse: true, axisTick: { show: false }, splitLine: { show: false },
        axisLabel: { color: c.tenue, fontSize: 9, interval: 0 } }),
      // Una sola serie con el color puesto caja por caja. Con una serie por señal habría que
      // dejar en `null` las cajas ajenas, y ECharts no acepta nulos en un boxplot: revienta al
      // construir la opción y la etapa entera queda sin vista.
      series: [{
        type: 'boxplot', boxWidth: [4, 11],
        data: cajas.map((k) => ({
          value: k.caja,
          itemStyle: { color: Grafico.paleta.varCss('--fondo-2'), borderWidth: 1.4,
                       borderColor: Grafico.paleta.serie(senales.indexOf(senal(k.nombre))) },
        })),
      }],
    }),
    pie: `${cajas.length} características, una por fila y coloreadas por señal (` +
         senales.map((sn, i) => `${sn}`).join(' · ') +
         '). Los bigotes llegan hasta 1,5 veces el rango intercuartílico; lo que queda afuera son ' +
         'los tramos extremos, que es justamente lo que se busca.',
  });
}

function verFiltrado(d) {
  const cuenta = (m) => d.motivo.filter((x) => x === m).length;
  $('#fase-visual').innerHTML = `<div class="resumen-grid" style="margin-top:0">
      <div class="celda"><div class="v">${cuenta('poca variación')}</div><div class="r">se van por poca variación</div></div>
      <div class="celda"><div class="v">${cuenta('repite a otra')}</div><div class="r">se van por repetir a otra</div></div>
    </div>
    <h4 style="font-size:.88rem;margin:20px 0 4px">Por qué se cae cada una</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:6px">El filtro mira el <strong>rango
    intercuartílico</strong>: cuánto se mueve la característica entre el tramo típico bajo y el típico
    alto. Las que casi no se mueven no distinguen nada. La línea punteada es el corte real — el
    percentil ${d.percentil} de todas — y a su izquierda quedan las descartadas por eso. Ojo con el
    orden: los dos filtros van en cadena, así que lo que se cae por acá ni siquiera llega a
    compararse con las demás.</p>
    <div id="caja-iqr"></div>
    <h4 style="font-size:.88rem;margin:22px 0 4px">Y cuáles repiten a otra</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:6px">Cada celda es cuánto se mueven juntas
    dos características. Donde hay un bloque intenso fuera de la diagonal, esas dicen lo mismo: de
    cada grupo con correlación ${d.umbral_correlacion} o más sobrevive una sola. Los rótulos en
    negrita son las conservadas.</p>
    <div id="caja-corr"></div>`;
  iqrDeFeatures($('#caja-iqr'), d);
  correlacionDeFeatures($('#caja-corr'), d);
}

const COLOR_MOTIVO = { 'conservada': 0, 'poca variación': 4, 'repite a otra': 2 };

/** Rango intercuartílico por característica, ordenado, con el corte real marcado. */
function iqrDeFeatures(destino, d) {
  const corto = (n) => n.replace('__', ' · ');
  // Ordenadas por IQR: así las descartadas quedan juntas y el corte se ve como una frontera.
  const orden = d.features.map((n, i) => i).sort((a, b) => d.iqr[a] - d.iqr[b]);
  const nombres = orden.map((i) => corto(d.features[i]));
  const alto = orden.length * 15 + 80;
  Grafico.medida(destino, {
    titulo: 'Cuánto se mueve cada característica',
    alto,
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 200, right: 30, top: 12, bottom: 46 },
      tooltip: Object.assign({}, c.tooltip, { trigger: 'item',
        formatter: (p) => {
          const i = orden[p.dataIndex];
          return `<b>${Grafico.paleta.fmt(d.iqr[i], 5)}</b> de rango intercuartílico<br>` +
                 `<span style="color:${c.tenue}">${corto(d.features[i])} · ${d.motivo[i]}</span>`;
        } }),
      // Escala logarítmica: los rangos van de milésimas a millones y en lineal se aplastan todos
      // contra el cero, que es donde justamente hay que mirar.
      xAxis: Object.assign({}, c.eje, { type: 'log', name: 'rango intercuartílico (escala log)',
        nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: c.tenue } }),
      yAxis: Object.assign({}, c.eje, { type: 'category', data: nombres, inverse: true,
        axisTick: { show: false },
        // Guías tenues en vez de barras: en un eje logarítmico una barra codifica un largo desde
        // cero, y el cero no existe ahí, así que el largo no querría decir nada. El punto codifica
        // posición, que es lo único legítimo en esta escala.
        splitLine: { show: true, lineStyle: { color: c.borde, opacity: .35 } },
        axisLabel: { color: c.tenue, fontSize: 9, interval: 0 } }),
      series: [{
        type: 'scatter', symbolSize: 9,
        data: orden.map((i) => ({
          value: Math.max(d.iqr[i], 1e-9),
          itemStyle: { color: Grafico.paleta.serie(COLOR_MOTIVO[d.motivo[i]] ?? 0) },
        })),
        markLine: d.corte_percentil ? {
          silent: true, symbol: 'none',
          label: { formatter: `corte · percentil ${d.percentil}`, color: c.tenue, fontSize: 10 },
          lineStyle: { color: c.tenue, type: 'dashed' },
          data: [{ xAxis: d.corte_percentil }],
        } : undefined,
      }],
    }),
    pie: 'Azul: conservada · violeta: descartada por poca variación · ámbar: descartada por repetir a otra.',
  });
}

/** Mapa de correlación de las 72, con las conservadas destacadas en el rótulo. */
function correlacionDeFeatures(destino, d) {
  const f = d.features;
  const corto = (n) => n.replace('__', ' · ');
  const celdas = [];
  d.correlacion.forEach((fila, i) => fila.forEach((v, j) => celdas.push([j, i, v])));
  Grafico.medida(destino, {
    alto: Math.max(420, Math.min(780, f.length * 9 + 150)),
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 200, right: 18, top: 34, bottom: 12 },
      tooltip: Object.assign({}, c.tooltip, {
        formatter: (p) => `<b>${Grafico.paleta.fmt(p.data[2], 2)}</b> de correlación<br>` +
          `<span style="color:${c.tenue}">${corto(f[p.data[1]])}<br>${corto(f[p.data[0]])}</span>`,
      }),
      // Divergente: dos tonos con un neutro en el cero, porque la correlación tiene signo.
      visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', top: 0,
        itemWidth: 12, precision: 2, textStyle: { color: c.tenue, fontSize: 10 },
        inRange: { color: [Grafico.paleta.serie(0), Grafico.paleta.varCss('--fondo-2'),
                           Grafico.paleta.serie(3)] } },
      xAxis: { type: 'category', data: f, axisTick: { show: false },
               axisLine: { lineStyle: { color: c.borde } }, axisLabel: { show: false } },
      yAxis: { type: 'category', data: f, inverse: true, axisTick: { show: false },
        axisLine: { lineStyle: { color: c.borde } },
        axisLabel: { fontSize: 9, interval: 0,
          formatter: (v, i) => (d.motivo[i] === 'conservada' ? `{ok|${corto(v)}}` : `{no|${corto(v)}}`),
          rich: { ok: { color: c.tinta, fontWeight: 600, fontSize: 9 },
                  no: { color: c.tenue, opacity: .55, fontSize: 9 } } } },
      series: [{ type: 'heatmap', data: celdas, progressive: 2000 }],
    }),
  });
}

function verScores(d) {
  $('#fase-visual').innerHTML = `<h4 style="font-size:.92rem;margin:0 0 4px">Cómo se reparten los puntajes</h4>
    <p class="tenue" style="font-size:.8rem;margin-bottom:8px">De izquierda a derecha, los tramos
    ordenados del menos raro al más raro. Lo que importa es la forma: una curva que se dispara al final
    significa que ese método separa con claridad unos pocos tramos del resto; una recta significa que
    reparte parejo y distingue poco. Cada método va en <strong>su propio panel</strong> justamente
    porque cada uno tiene su escala: las alturas no se comparan entre paneles, y ahora eso se ve en vez
    de estar solo aclarado acá.</p><div id="caja-perc"></div>
    <h4 style="font-size:.88rem;margin:18px 0 8px">Los tramos más extremos según cada método</h4>
    <div class="mini">${d.detectores.map((det, i) => `
      <div class="caja"><h5 style="color:var(--serie-${(i % 5) + 1})">${det}</h5>
      <table style="font-size:.76rem"><tbody>${d.top[det].slice(0, 6).map((t) =>
        `<tr><td>${t.hoja}</td><td class="num">${t.inicio}</td>
         <td class="num" style="color:var(--acento-2)">${t.score.toFixed(2)}</td></tr>`).join('')}
      </tbody></table></div>`).join('')}</div>`;
  Grafico.lineas($('#caja-perc'), {
    titulo: 'Distribución de puntajes, un panel por método',
    altoPanel: 68,
    xNombre: 'percentil',
    formatoX: (i) => `${i * 5}%`,
    sustantivo: 'percentiles',
    paneles: d.detectores.map((c) => ({ nombre: c, valores: d.percentiles[c] })),
  });
}

function verEventos(d) {
  const cols = ['event_id', 'SheetName', 'start', 'end', 'n_ventanas', 'n_detectores', 'features_top']
    .filter((c) => d.columnas.includes(c));
  const filas = [...d.filas].sort((a, b) => b.n_detectores - a.n_detectores || b.n_ventanas - a.n_ventanas);
  const rot = { n_detectores: 'métodos', n_ventanas: 'tramos', SheetName: 'hoja', event_id: 'id',
                start: 'desde', end: 'hasta', features_top: 'qué se desvió' };
  $('#fase-visual').innerHTML = `
    <div class="aviso info" style="font-size:.82rem;margin-bottom:12px">
      <strong>Cómo leer «métodos».</strong> «4/5» quiere decir que cuatro de los cinco marcaron
      <em>al menos un tramo</em> dentro del evento — no que coincidieran en el mismo. Un evento largo
      tiene más chances de juntar métodos distintos. En «qué se desvió», el número está en desvíos
      respecto de lo normal: +9 es muchísimo, +2 es notorio pero no extremo.</div>
    <div class="descargas">
      <div>
        <h4 style="font-size:.92rem;margin:0 0 2px">Llevarse el entregable</h4>
        <p class="tenue" style="font-size:.78rem;margin:0">Los mismos Excel que produce el pipeline de
        la tesis, pero con <strong>la configuración de esta rama</strong>. Cada archivo abre con una
        hoja que dice de dónde salió y si coincide con la configuración firmada.</p>
      </div>
      <span class="esp"></span>
      <a class="boton" download href="/api/nodo/${S.sel}/excel/experto"
         title="Candidatos consolidados, con el porqué de cada evento">Para el experto</a>
      <a class="boton" download href="/api/nodo/${S.sel}/excel/presentable"
         title="Versión con formato, tiempo real y gráficos">Presentable</a>
      <a class="boton" download href="/api/nodo/${S.sel}/excel/normales"
         title="Ventanas normales, para contrastar contra las candidatas">Contraste normal</a>
    </div>
    <div class="fila-sup"><h4 style="font-size:.92rem">Eventos candidatos (${filas.length})</h4>
      <span class="esp"></span>
      <span class="tenue" style="font-size:.78rem">clic en una fila para ver sus señales</span></div>
    <div id="caja-linea" style="margin-bottom:18px"></div>
    <div class="tabla-scroll"><table><thead><tr>${cols.map((c) =>
      `<th>${rot[c] || c}</th>`).join('')}</tr></thead>
    <tbody>${filas.map((f) => `<tr data-ev="${f.event_id}" style="cursor:pointer">${cols.map((c) => {
      const v = f[c];
      if (c === 'n_detectores') return `<td class="num"><strong style="color:${v >= 4 ? 'var(--acento-2)' : 'var(--texto-2)'}">${v}/5</strong></td>`;
      if (c === 'features_top') return `<td class="mono" style="font-size:.71rem;color:var(--texto-2)">${(v || '').slice(0, 60)}</td>`;
      return typeof v === 'number' ? `<td class="num">${v}</td>` : `<td>${v}</td>`;
    }).join('')}</tr>`).join('')}</tbody></table></div>
    <div id="detalle-evento" style="margin-top:16px"></div>`;
  lineaDeEventos($('#caja-linea'), d, filas);
  document.querySelectorAll('#fase-visual tr[data-ev]').forEach((tr) =>
    tr.addEventListener('click', () => verEvento(Number(tr.dataset.ev))));
}

/** Dónde cae cada evento a lo largo del registro de su hoja.
 *
 *  La tabla dice cuántos eventos hay y con qué fuerza, pero no dónde. Y «dónde» es lo primero que
 *  se quiere mirar: si se amontonan en una hoja, si caen al principio de la sesión, si hay hojas
 *  enteras sin nada. Cada hoja es una pista gris con el largo de su registro, y encima los eventos.
 */
function lineaDeEventos(destino, d, filas) {
  const pistas = d.pistas || [];
  if (!pistas.length || !filas.length) return;

  const conEventos = new Set(filas.map((f) => f.SheetName));
  const usadas = pistas.filter((p) => conEventos.has(p.hoja));
  const vacias = pistas.length - usadas.length;
  const fila = new Map(usadas.map((p, i) => [p.hoja, i]));
  const maxDet = Math.max(...filas.map((f) => f.n_detectores), 1);
  const alto = usadas.length * 26 + 76;

  Grafico.medida(destino, {
    titulo: 'Dónde cae cada evento',
    alto,
    opcion: (c) => {
      const pista = (params, api) => {
        const y = api.coord([0, api.value(0)])[1];
        const x0 = api.coord([api.value(1), api.value(0)])[0];
        const x1 = api.coord([api.value(2), api.value(0)])[0];
        return { type: 'rect', shape: { x: x0, y: y - 3, width: Math.max(1, x1 - x0), height: 6 },
                 style: { fill: c.borde } };
      };
      const evento = (params, api) => {
        const y = api.coord([0, api.value(0)])[1];
        const x0 = api.coord([api.value(1), api.value(0)])[0];
        const x1 = api.coord([api.value(2), api.value(0)])[0];
        const n = api.value(3);
        return { type: 'rect',
                 shape: { x: x0, y: y - 9, width: Math.max(3, x1 - x0), height: 18, r: 3 },
                 style: { fill: Grafico.paleta.serie(n >= 4 ? 1 : 0),
                          opacity: .35 + .65 * (n / maxDet) } };
      };
      return {
        animation: false,
        textStyle: c.textStyle,
        grid: { left: 130, right: 26, top: 12, bottom: 46 },
        tooltip: Object.assign({}, c.tooltip, {
          formatter: (p) => (p.seriesIndex === 0 ? null
            : `<b>Evento ${p.value[4]}</b> · ${p.value[3]} de 5 métodos<br>` +
              `<span style="color:${c.tenue}">${usadas[p.value[0]].hoja} · mediciones ` +
              `${p.value[1]}–${p.value[2]}</span>`),
        }),
        xAxis: Object.assign({}, c.eje, { type: 'value', min: 0,
          name: 'medición dentro de la hoja', nameLocation: 'middle', nameGap: 26,
          nameTextStyle: { color: c.tenue } }),
        yAxis: Object.assign({}, c.eje, { type: 'category',
          data: usadas.map((p) => p.hoja), inverse: true,
          axisTick: { show: false }, splitLine: { show: false },
          axisLabel: { color: c.tenue, fontSize: 10 } }),
        series: [
          { type: 'custom', renderItem: pista, silent: true,
            encode: { x: [1, 2], y: 0 },
            data: usadas.map((p, i) => [i, p.desde, p.hasta]) },
          { type: 'custom', renderItem: evento,
            encode: { x: [1, 2], y: 0 },
            data: filas.filter((f) => fila.has(f.SheetName))
                       .map((f) => [fila.get(f.SheetName), f.start, f.end, f.n_detectores, f.event_id]) },
        ],
      };
    },
    pie: `${filas.length} eventos repartidos en ${usadas.length} hojas` +
         (vacias ? `; las otras ${vacias} hojas no tienen ninguno.` : '.') +
         ' Cuanto más intenso el bloque, más métodos coinciden.',
  });
}

async function verEvento(id) {
  const cont = $('#detalle-evento');
  cont.innerHTML = '<p class="tenue" style="font-size:.84rem">Cargando…</p>';
  try {
    const d = await api(`/api/nodo/${S.sel}/evento/${id}`);
    const ev = d.evento;
    cont.innerHTML = `<div style="background:var(--fondo-2);border:1px solid var(--borde);
        border-radius:10px;padding:14px">
      <div class="fila-sup"><h4 style="font-size:.9rem">Evento ${id} · ${ev.SheetName}</h4>
        <span class="chip ${ev.n_detectores >= 4 ? 'listo' : 'pendiente'}">${ev.n_detectores}/5 métodos</span>
        <span class="esp"></span><span class="mono tenue" style="font-size:.76rem">
        mediciones ${ev.start}–${ev.end} · ${ev.n_ventanas} tramos</span></div>
      <div id="caja-ev"></div>
      <p class="mono tenue" style="font-size:.74rem;margin-top:8px">${ev.features_top || ''}</p></div>`;
    Grafico.lineas($('#caja-ev'), {
      titulo: `Señales del evento ${id}`,
      xNombre: 'medición',
      sustantivo: 'mediciones',
      paneles: d.senales.map((s, i) => ({ nombre: s, valores: d.valores.map((f) => f[i]) })),
    });
  } catch (e) {
    cont.innerHTML = `<p class="tenue" style="font-size:.84rem">No se pudo cargar: ${e.message}</p>`;
  }
}

iniciar().catch((e) => document.querySelector('.envoltorio').insertAdjacentHTML('afterbegin',
  `<div class="aviso" style="margin:20px 0"><strong>No se pudo iniciar:</strong> ${e.message}</div>`));

/* Taller Etapa 1 — lógica del frontend.
 *
 * No calcula nada del pipeline: arma formularios a partir de las etapas que declara el backend,
 * dispara ejecuciones y dibuja los resultados. Toda la ciencia ocurre del lado del servidor,
 * llamando al paquete `tesis`.
 */

const estado = {
  etapas: [],        // definición de etapas que envía el backend
  cadena: [],        // nombres de etapas en orden
  nodos: [],         // árbol completo
  seleccionado: null, // clave del nodo seleccionado (el padre de lo próximo que se ejecute)
  etapaActual: null,
  sondeo: null,
};

const $ = (s) => document.querySelector(s);
const api = async (ruta, opciones) => {
  const r = await fetch(ruta, opciones);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
};

// --------------------------------------------------------------------------- arranque
async function iniciar() {
  const def = await api('/api/etapas');
  estado.etapas = def.etapas;
  estado.cadena = def.cadena;

  const est = await api('/api/estado');
  $('#sello').textContent = `tesis @ ${est.commit_tesis}`;
  if (!est.datos_listos) {
    $('#alerta-datos').innerHTML = `<div class="aviso" style="margin:16px 0">
      <strong>Faltan los datos base.</strong> Generalos una vez con
      <span class="mono">python scripts/exportar_crudo.py</span> y recargá esta página.</div>`;
  }

  await refrescarArbol();
  seleccionar(null);

  $('#btn-ejecutar').addEventListener('click', ejecutar);
  $('#btn-reiniciar').addEventListener('click', () => seleccionar(null));
}

// --------------------------------------------------------------------------- árbol
async function refrescarArbol() {
  const { nodos } = await api('/api/arbol');
  estado.nodos = nodos;
  const cont = $('#arbol');
  if (!nodos.length) {
    cont.innerHTML = '<p class="tenue" style="font-size:.85rem">Sin ejecuciones todavía.</p>';
    return;
  }
  // Orden jerárquico: cada nodo debajo de su padre, con sangría por profundidad
  const hijos = new Map();
  nodos.forEach((n) => {
    const k = n.padre || '__raiz__';
    if (!hijos.has(k)) hijos.set(k, []);
    hijos.get(k).push(n);
  });
  const partes = [];
  const recorrer = (clave, nivel) => {
    (hijos.get(clave) || []).forEach((n) => {
      const sel = n.clave === estado.seleccionado ? ' sel' : '';
      partes.push(`<div class="nodo${sel}" data-clave="${n.clave}" style="margin-left:${nivel * 12}px">
        <div>
          <div class="etapa">${n.etapa}</div>
          <div class="detalle">${resumenCorto(n)}</div>
        </div>
        <span class="chip ${n.estado}">${n.estado}</span>
      </div>`);
      recorrer(n.clave, nivel + 1);
    });
  };
  recorrer('__raiz__', 0);
  cont.innerHTML = partes.join('');
  cont.querySelectorAll('.nodo').forEach((el) =>
    el.addEventListener('click', () => seleccionar(el.dataset.clave)));
}

function resumenCorto(n) {
  const p = n.parametros || {};
  const claves = {
    datos: () => `limpieza ${p.limpiar ? 'sí' : 'no'}`,
    ventaneo: () => `v${p.tamano_ventana}/p${p.paso}${p.deduplicar ? ` · dedup ${p.umbral_dedup}` : ''}`,
    features: () => `${p.rezagos_autocorr} rezagos`,
    filtrado: () => `corr ${p.umbral_correlacion}`,
    deteccion: () => `${(p.detectores || []).length} detectores`,
    eventos: () => `${(p.fraccion_candidatos * 100).toFixed(1)}% · máx ${p.max_ventanas_evento || '∞'}`,
  };
  const base = (claves[n.etapa] || (() => ''))();
  return n.duracion_s ? `${base} · ${n.duracion_s}s` : base;
}

// --------------------------------------------------------------------------- selección
function seleccionar(clave) {
  estado.seleccionado = clave;
  const nodo = estado.nodos.find((n) => n.clave === clave);
  const etapaPadre = nodo ? nodo.etapa : null;
  const i = etapaPadre ? estado.cadena.indexOf(etapaPadre) + 1 : 0;
  estado.etapaActual = i < estado.cadena.length ? estado.cadena[i] : null;

  pintarBarraEtapas(etapaPadre);
  pintarCadena(clave);
  pintarFormulario();
  refrescarArbol();

  if (nodo && nodo.estado === 'listo') mostrarResultado(clave);
  else $('#panel-resultado').style.display = 'none';
}

function pintarBarraEtapas(etapaPadre) {
  const hechas = etapaPadre ? estado.cadena.indexOf(etapaPadre) + 1 : 0;
  $('#barra-etapas').innerHTML = estado.cadena.map((e, idx) => {
    const cls = idx < hechas ? 'hecha' : (e === estado.etapaActual ? 'actual' : '');
    return `<span class="et ${cls}">${idx + 1}. ${e}</span>`;
  }).join('');
}

function pintarCadena(clave) {
  const cont = $('#cadena');
  if (!clave) { cont.innerHTML = '<span class="tenue" style="font-size:.82rem">Rama nueva desde los datos crudos.</span>'; return; }
  const cadena = [];
  let actual = estado.nodos.find((n) => n.clave === clave);
  while (actual) {
    cadena.unshift(actual);
    actual = estado.nodos.find((n) => n.clave === actual.padre);
  }
  cont.innerHTML = cadena.map((n) =>
    `<span class="eslabon">${n.etapa}: ${resumenCorto(n)}</span>`).join('<span class="flecha">→</span>');
}

// --------------------------------------------------------------------------- formulario
function pintarFormulario() {
  const cont = $('#formulario');
  if (!estado.etapaActual) {
    $('#titulo-etapa').textContent = 'Cadena completa';
    $('#desc-etapa').textContent = 'Esta rama llegó hasta el final. Elegí un nodo anterior para ramificar desde ahí.';
    cont.innerHTML = '';
    $('#btn-ejecutar').disabled = true;
    return;
  }
  const def = estado.etapas.find((e) => e.nombre === estado.etapaActual);
  $('#titulo-etapa').textContent = def.titulo;
  $('#desc-etapa').textContent = def.descripcion;
  $('#btn-ejecutar').disabled = false;

  cont.innerHTML = def.parametros.map((p) => {
    const id = `p_${p.nombre}`;
    if (p.tipo === 'booleano') {
      return `<div class="campo"><label class="interruptor">
        <input type="checkbox" id="${id}" ${p.defecto ? 'checked' : ''}> ${p.etiqueta}</label>
        ${p.ayuda ? `<div class="ayuda">${p.ayuda}</div>` : ''}</div>`;
    }
    if (p.tipo === 'multiple') {
      const ops = p.opciones || p.defecto || [];
      const marcadas = new Set(p.defecto || []);
      return `<div class="campo"><label>${p.etiqueta}</label><div class="opciones">
        ${ops.map((o) => `<label><input type="checkbox" name="${id}" value="${o}"
           ${marcadas.has(o) ? 'checked' : ''}> ${o}</label>`).join('')}
        </div>${p.ayuda ? `<div class="ayuda">${p.ayuda}</div>` : ''}</div>`;
    }
    const paso = p.tipo === 'decimal' ? 'any' : '1';
    return `<div class="campo"><label for="${id}">${p.etiqueta}</label>
      <input type="number" id="${id}" value="${p.defecto}" step="${paso}"
        ${p.minimo != null ? `min="${p.minimo}"` : ''} ${p.maximo != null ? `max="${p.maximo}"` : ''}>
      ${p.ayuda ? `<div class="ayuda">${p.ayuda}</div>` : ''}</div>`;
  }).join('');
}

function leerFormulario() {
  const def = estado.etapas.find((e) => e.nombre === estado.etapaActual);
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

// --------------------------------------------------------------------------- ejecución
async function ejecutar() {
  const cuerpo = {
    etapa: estado.etapaActual,
    padre: estado.seleccionado,
    parametros: leerFormulario(),
  };
  $('#btn-ejecutar').disabled = true;
  $('#estado-ejecucion').textContent = 'Encolando…';
  try {
    const r = await api('/api/ejecutar', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cuerpo),
    });
    if (r.reutilizado) {
      $('#estado-ejecucion').textContent = 'Ya estaba calculado — reutilizado del caché.';
      await refrescarArbol();
      seleccionar(r.clave);
      $('#btn-ejecutar').disabled = false;
      return;
    }
    sondear(r.clave);
  } catch (e) {
    $('#estado-ejecucion').textContent = `Error: ${e.message}`;
    $('#btn-ejecutar').disabled = false;
  }
}

function sondear(clave) {
  clearInterval(estado.sondeo);
  const desde = Date.now();
  estado.sondeo = setInterval(async () => {
    const n = await api(`/api/nodo/${clave}`);
    const seg = ((Date.now() - desde) / 1000).toFixed(0);
    $('#estado-ejecucion').textContent = `${n.estado}… ${seg}s`;
    await refrescarArbol();
    if (n.estado === 'listo' || n.estado === 'error') {
      clearInterval(estado.sondeo);
      $('#btn-ejecutar').disabled = false;
      if (n.estado === 'error') {
        $('#estado-ejecucion').innerHTML = '<span style="color:var(--peligro)">Falló — ver detalle abajo</span>';
        $('#panel-resultado').style.display = 'block';
        $('#resumen').innerHTML = '';
        $('#visual').innerHTML = `<pre class="mono" style="white-space:pre-wrap;color:var(--peligro);font-size:.8rem">${n.error}</pre>`;
        return;
      }
      $('#estado-ejecucion').textContent = `Listo en ${n.duracion_s}s`;
      seleccionar(clave);
    }
  }, 900);
}

// --------------------------------------------------------------------------- resultados
async function mostrarResultado(clave) {
  const nodo = estado.nodos.find((n) => n.clave === clave);
  if (!nodo || !nodo.resumen) { $('#panel-resultado').style.display = 'none'; return; }
  $('#panel-resultado').style.display = 'block';

  $('#resumen').innerHTML = Object.entries(nodo.resumen)
    .filter(([, v]) => typeof v !== 'object' || Array.isArray(v))
    .map(([k, v]) => `<div class="celda"><div class="v">${formatear(v)}</div>
      <div class="r">${k.replace(/_/g, ' ')}</div></div>`).join('');

  try {
    const datos = await api(`/api/nodo/${clave}/datos`);
    $('#visual').innerHTML = '';
    if (datos.tipo === 'ventanas' || datos.tipo === 'series') dibujarBarras(datos.por_hoja, 'Filas/ventanas por hoja');
    else if (datos.tipo === 'scores') dibujarPercentiles(datos);
    else if (datos.tipo === 'eventos') dibujarEventos(datos);
    else if (datos.tipo === 'features') {
      $('#visual').innerHTML = `<p class="tenue" style="font-size:.87rem">${datos.total} características:</p>
        <div class="mono" style="font-size:.76rem;color:var(--texto-2);max-height:150px;overflow:auto">
        ${datos.columnas.join(' · ')}</div>`;
    }
  } catch { /* sin visual para esta etapa */ }
}

const formatear = (v) => Array.isArray(v) ? v.length
  : (typeof v === 'number' ? v.toLocaleString('es') : (v === true ? 'sí' : v === false ? 'no' : v));

function lienzo(alto = 220) {
  const c = document.createElement('canvas');
  c.width = $('#visual').clientWidth * 2;
  c.height = alto * 2;
  c.style.height = `${alto}px`;
  $('#visual').appendChild(c);
  const ctx = c.getContext('2d');
  ctx.scale(2, 2);
  return { ctx, ancho: c.width / 2, alto };
}

function dibujarBarras(mapa, titulo) {
  $('#visual').insertAdjacentHTML('beforeend', `<h4 style="margin:0 0 8px;font-size:.9rem">${titulo}</h4>`);
  const { ctx, ancho, alto } = lienzo(200);
  const ent = Object.entries(mapa);
  const max = Math.max(...ent.map(([, v]) => v));
  const w = ancho / ent.length;
  ent.forEach(([k, v], i) => {
    const h = (v / max) * (alto - 46);
    const g = ctx.createLinearGradient(0, alto - h - 24, 0, alto - 24);
    g.addColorStop(0, '#7ef0c0'); g.addColorStop(1, '#4ea8ff');
    ctx.fillStyle = g;
    ctx.fillRect(i * w + 3, alto - h - 24, w - 6, h);
    ctx.save();
    ctx.translate(i * w + w / 2, alto - 16);
    ctx.rotate(-Math.PI / 9);
    ctx.fillStyle = '#93a4c0'; ctx.font = '9px system-ui'; ctx.textAlign = 'right';
    ctx.fillText(k.slice(0, 14), 0, 0);
    ctx.restore();
  });
}

function dibujarPercentiles(datos) {
  $('#visual').insertAdjacentHTML('beforeend',
    `<h4 style="margin:0 0 4px;font-size:.9rem">Distribución de puntajes (percentiles)</h4>
     <p class="tenue" style="font-size:.8rem;margin-bottom:8px">Cada curva está normalizada a su propio
     máximo: las escalas de los detectores <strong>no son comparables entre sí</strong>.</p>`);
  const { ctx, ancho, alto } = lienzo(230);
  const colores = ['#4ea8ff', '#7ef0c0', '#ffc86b', '#ff8a5b', '#c58cff'];
  datos.detectores.forEach((d, i) => {
    const serie = datos.percentiles[d];
    const max = Math.max(...serie.map(Math.abs)) || 1;
    ctx.beginPath();
    serie.forEach((v, j) => {
      const x = (j / (serie.length - 1)) * (ancho - 30) + 15;
      const y = alto - 28 - (Math.abs(v) / max) * (alto - 60);
      j ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
    });
    ctx.strokeStyle = colores[i % colores.length];
    ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = colores[i % colores.length];
    ctx.font = '10px system-ui';
    ctx.fillText(d, 16 + i * 78, 14);
  });
  ctx.fillStyle = '#93a4c0'; ctx.font = '9px system-ui';
  ctx.fillText('percentil 0', 12, alto - 10);
  ctx.textAlign = 'right'; ctx.fillText('100', ancho - 12, alto - 10);
}

function dibujarEventos(datos) {
  const cols = ['event_id', 'SheetName', 'start', 'end', 'n_ventanas', 'n_detectores', 'features_top'];
  const usar = cols.filter((c) => datos.columnas.includes(c));
  const filas = datos.filas.sort((a, b) => b.n_detectores - a.n_detectores);
  $('#visual').innerHTML = `<h4 style="margin:0 0 8px;font-size:.9rem">Eventos candidatos</h4>
    <div class="tabla-scroll"><table><thead><tr>
      ${usar.map((c) => `<th>${c}</th>`).join('')}</tr></thead><tbody>
      ${filas.map((f) => `<tr>${usar.map((c) => {
        const v = f[c];
        if (c === 'n_detectores') return `<td class="num"><strong style="color:${v >= 4 ? 'var(--acento-2)' : 'var(--texto-2)'}">${v}/5</strong></td>`;
        if (c === 'features_top') return `<td class="mono" style="font-size:.72rem;color:var(--texto-2)">${(v || '').slice(0, 70)}</td>`;
        return typeof v === 'number' ? `<td class="num">${v}</td>` : `<td>${v}</td>`;
      }).join('')}</tr>`).join('')}
    </tbody></table></div>`;
}

iniciar().catch((e) => {
  document.querySelector('.envoltorio').insertAdjacentHTML('afterbegin',
    `<div class="aviso" style="margin:20px 0"><strong>No se pudo iniciar:</strong> ${e.message}</div>`);
});

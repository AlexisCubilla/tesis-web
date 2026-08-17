/* Pantalla de análisis: los cuatro cortes que el taller no mostraba.
 *
 * No calcula nada. Pide `/api/nodo/{clave}/analisis` y dibuja. Todo lo que tenga que ver con
 * «qué tramo está marcado» lo decide el backend preguntándoselo al paquete de la tesis, para que
 * no haya dos reglas que puedan separarse con el tiempo.
 */

const $ = (s) => document.querySelector(s);
const api = async (ruta) => {
  const r = await fetch(ruta);
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
  return r.json();
};
const V = Grafico.paleta;
const miles = (v) => Number(v).toLocaleString('es');

const S = { nodos: [], clave: null, datos: null, detector: null };

// ============================================================================ arranque
async function iniciar() {
  try {
    S.nodos = (await api('/api/arbol')).nodos;
  } catch (e) {
    return avisar(`No se pudo leer el árbol de ejecuciones: ${e.message}`);
  }

  // Solo sirven los nodos que ya tienen puntajes: detección en adelante.
  const utiles = S.nodos.filter((n) => n.estado === 'listo'
    && ['deteccion', 'eventos'].includes(n.etapa));
  if (!utiles.length) {
    return avisar('Todavía no hay ninguna rama con puntajes. Corré al menos hasta el paso 5 ' +
                  '(detección) en el taller — o usá «★ Correr la de la tesis».', 'info');
  }

  const sel = $('#sel-rama');
  sel.replaceChildren();
  for (const n of utiles) {
    const o = document.createElement('option');
    o.value = n.clave;
    o.textContent = `${etiqueta(n)} · paso ${n.etapa} · ${n.clave.slice(0, 8)}`;
    sel.appendChild(o);
  }
  sel.addEventListener('change', () => cargar(sel.value));
  $('#sel-det').addEventListener('change', (e) => {
    S.detector = e.target.value;
    cargar(S.clave, S.detector);
  });
  cargar(utiles[0].clave);
}

/** Un rótulo corto y humano para la rama, con los parámetros que la distinguen. */
function etiqueta(n) {
  const p = n.parametros || {};
  const trozos = [];
  if (p.detectores) trozos.push(`${p.detectores.length} métodos`);
  if (p.fraccion_candidatos != null) trozos.push(`${(p.fraccion_candidatos * 100).toFixed(1)} %`);
  if (p.max_ventanas_evento) trozos.push(`tope ${p.max_ventanas_evento}`);
  return trozos.join(' · ') || n.etapa;
}

function avisar(texto, clase = '') {
  $('#tablero').hidden = true;
  const d = document.createElement('div');
  d.className = `aviso ${clase}`;
  d.style.margin = '16px 0';
  d.textContent = texto;
  $('#aviso').replaceChildren(d);
}

async function cargar(clave, detector) {
  S.clave = clave;
  $('#aviso').replaceChildren();
  const cargando = document.createElement('p');
  cargando.className = 'tenue';
  cargando.style.fontSize = '.85rem';
  cargando.textContent = 'Calculando…';
  $('#aviso').appendChild(cargando);
  try {
    const url = `/api/nodo/${clave}/analisis` + (detector ? `?detector=${encodeURIComponent(detector)}` : '');
    S.datos = await api(url);
  } catch (e) {
    return avisar(`No se pudo analizar esta rama: ${e.message}`);
  }
  $('#aviso').replaceChildren();
  $('#tablero').hidden = false;
  pintar();
}

function pintar() {
  const d = S.datos;
  S.detector = d.detector;

  const sd = $('#sel-det');
  sd.replaceChildren();
  for (const nombre of d.detectores) {
    const o = document.createElement('option');
    o.value = nombre;
    o.textContent = nombre;
    o.selected = nombre === d.detector;
    sd.appendChild(o);
  }

  cifras(d);
  Grafico.limpiar($('#tablero'));
  coincidencia(d);
  reparto(d);
  puntajes(d);
  dispersion(d);
  correlacion(d);
}

function cifras(d) {
  const cont = $('#cifras');
  cont.replaceChildren();
  const marcados = Object.values(d.coincidencia.reparto).reduce((a, b) => a + b, 0);
  const acuerdo = Object.entries(d.coincidencia.reparto)
    .filter(([k]) => Number(k) >= 4).reduce((a, [, v]) => a + v, 0);
  const filas = [
    [miles(d.n_ventanas), 'tramos evaluados'],
    [miles(d.top_k), `marca cada método (${(d.fraccion_candidatos * 100).toFixed(1)} %)`],
    [miles(marcados), 'tramos marcados por alguno'],
    [miles(acuerdo), 'con 4 o 5 métodos de acuerdo'],
  ];
  for (const [v, r] of filas) {
    const c = document.createElement('div');
    c.className = 'celda';
    const a = document.createElement('div'); a.className = 'v'; a.textContent = v;
    const b = document.createElement('div'); b.className = 'r'; b.textContent = r;
    c.append(a, b);
    cont.appendChild(c);
  }
}

// ---------------------------------------------------------------- 1. coincidencia
function coincidencia(d) {
  const n = d.coincidencia.orden;
  const celdas = [];
  d.coincidencia.matriz.forEach((fila, i) =>
    fila.forEach((v, j) => celdas.push([j, i, v])));
  const max = Math.max(...celdas.map((c) => c[2]), 1);

  Grafico.medida($('#g-coincidencia'), {
    titulo: 'Tramos que marcan de a pares',
    alto: 330,
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 4, right: 12, top: 8, bottom: 4, containLabel: true },
      tooltip: Object.assign({}, c.tooltip, {
        formatter: (p) => (p.data[0] === p.data[1]
          ? `<b>${p.data[2]}</b> tramos marca ${n[p.data[0]]}`
          : `<b>${p.data[2]}</b> tramos marcan los dos<br>${n[p.data[1]]} y ${n[p.data[0]]}`),
      }),
      xAxis: { type: 'category', data: n, splitArea: { show: true },
               axisLabel: { color: c.tenue, rotate: 26, fontSize: 10 },
               axisLine: { lineStyle: { color: c.borde } }, axisTick: { show: false } },
      yAxis: { type: 'category', data: n, splitArea: { show: true }, inverse: true,
               axisLabel: { color: c.tenue, fontSize: 10 },
               axisLine: { lineStyle: { color: c.borde } }, axisTick: { show: false } },
      // Secuencial de un solo tono, claro → oscuro: es magnitud, no polaridad.
      visualMap: { min: 0, max, show: false,
                   inRange: { color: [V.varCss('--fondo-2'), V.serie(0)] } },
      series: [{
        type: 'heatmap', data: celdas,
        label: { show: true, color: c.tinta, fontSize: 11, fontFamily: 'ui-monospace, monospace',
                 formatter: (p) => p.data[2] },
        itemStyle: { borderColor: V.varCss('--panel'), borderWidth: 2 },
        emphasis: { itemStyle: { borderColor: V.varCss('--acento'), borderWidth: 2 } },
      }],
    }),
    pie: 'La diagonal es cuántos marca cada método por su cuenta: siempre el mismo número, porque ' +
         'cada uno marca su top del mismo tamaño.',
  });
}

// ---------------------------------------------------------------- 2. reparto del acuerdo
function reparto(d) {
  const claves = Object.keys(d.coincidencia.reparto).map(Number).sort((a, b) => a - b);
  const total = d.detectores.length;
  Grafico.medida($('#g-reparto'), {
    titulo: 'Cuántos métodos coinciden en un mismo tramo',
    alto: 330,
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 8, right: 22, top: 8, bottom: 24, containLabel: true },
      tooltip: Object.assign({}, c.tooltip, { trigger: 'item',
        formatter: (p) => `<b>${p.value}</b> tramos los marca${p.name === '1' ? '' : 'n'} ${p.name} de ${total}` }),
      xAxis: Object.assign({}, c.eje, { type: 'category', data: claves.map(String),
        name: 'métodos de acuerdo', nameLocation: 'middle', nameGap: 26,
        nameTextStyle: { color: c.tenue }, splitLine: { show: false } }),
      yAxis: Object.assign({}, c.eje, { type: 'value', name: 'tramos', nameTextStyle: { color: c.tenue } }),
      series: [{
        type: 'bar', data: claves.map((k) => d.coincidencia.reparto[k]),
        barMaxWidth: 46,
        // El acuerdo alto es lo interesante: se resalta con el acento, el resto queda tenue.
        itemStyle: { borderRadius: [4, 4, 0, 0],
                     color: (p) => (claves[p.dataIndex] >= 4 ? V.serie(1) : V.serie(0)) },
        label: { show: true, position: 'top', color: c.tinta, fontFamily: 'ui-monospace, monospace' },
      }],
    }),
    pie: 'Que un tramo lo marquen 4 o 5 métodos distintos es la señal más fuerte que este trabajo ' +
         'puede dar sin etiquetas.',
  });
}

// ---------------------------------------------------------------- 3. distribución de puntajes
function puntajes(d) {
  const dets = d.detectores;
  const alto = dets.length * 122 + 64;
  Grafico.medida($('#g-puntajes'), {
    titulo: 'Distribución de puntajes, un panel por método',
    alto,
    opcion: (c) => {
      const grid = [], xAxis = [], yAxis = [], series = [];
      const paso = (alto - 40) / dets.length;
      dets.forEach((nombre, i) => {
        const p = d.puntajes[nombre];
        const centros = p.cuentas.map((_, k) => (p.bordes[k] + p.bordes[k + 1]) / 2);
        grid.push({ left: 62, right: 20, top: 28 + i * paso, height: paso - 46 });
        xAxis.push(Object.assign({}, c.eje, {
          type: 'category', gridIndex: i, data: centros.map((v) => V.fmt(v, 3)),
          axisLabel: { color: c.tenue, fontSize: 9, hideOverlap: true }, splitLine: { show: false },
        }));
        yAxis.push(Object.assign({}, c.eje, {
          type: 'value', gridIndex: i, name: nombre, nameLocation: 'end', nameGap: 7,
          nameTextStyle: { color: c.tinta, fontSize: 11, fontWeight: 600, align: 'left' },
          axisLine: { show: false }, axisTick: { show: false }, splitNumber: 2,
          axisLabel: { color: c.tenue, fontSize: 9 },
        }));
        // El corte cae en un borde de bin: se busca el índice más cercano para la línea.
        let iCorte = 0;
        centros.forEach((v, k) => { if (v <= p.corte) iCorte = k; });
        series.push({
          type: 'bar', xAxisIndex: i, yAxisIndex: i, data: p.cuentas,
          barCategoryGap: '12%', itemStyle: { color: V.serie(i) },
          markLine: {
            silent: true, symbol: 'none',
            label: { formatter: 'corte', color: c.tenue, fontSize: 9, position: 'insideEndTop' },
            lineStyle: { color: c.tenue, type: 'dashed', width: 1 },
            data: [{ xAxis: iCorte }],
          },
        });
      });
      return {
        animation: false, textStyle: c.textStyle, grid, xAxis, yAxis, series,
        tooltip: Object.assign({}, c.tooltip, {
          trigger: 'axis', axisPointer: { type: 'shadow' },
          formatter: (ps) => {
            const p = ps[0];
            const det = dets[p.seriesIndex];
            const q = d.puntajes[det].caja;
            return `<b>${p.value}</b> tramos con puntaje ≈ ${p.name}<br>` +
                   `<span style="color:${c.tenue}">${det} · mediana ${V.fmt(q[2], 3)} · ` +
                   `cuartiles ${V.fmt(q[1], 3)}–${V.fmt(q[3], 3)}</span>`;
          },
        }),
      };
    },
    pie: dets.map((n) => `${n}: ${d.puntajes[n].atipicos} tramos fuera de los bigotes`).join(' · '),
  });
}

// ---------------------------------------------------------------- 4. dispersión 2D
function dispersion(d) {
  const s = d.dispersion;
  const normales = [], marcados = [];
  for (let i = 0; i < s.x.length; i++) {
    (s.candidato[i] ? marcados : normales).push([s.x[i], s.y[i], s.puntaje[i], s.hoja[i]]);
  }
  const ve = s.varianza_explicada;
  Grafico.medida($('#g-dispersion'), {
    alto: 460,
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 52, right: 24, top: 16, bottom: 46 },
      tooltip: Object.assign({}, c.tooltip, {
        formatter: (p) => `<b>${V.fmt(p.data[2], 4)}</b> de puntaje<br>` +
                          `<span style="color:${c.tenue}">${p.data[3] || 'sin hoja'}</span>`,
      }),
      xAxis: Object.assign({}, c.eje, { type: 'value', scale: true,
        name: `componente 1 · ${(ve[0] * 100).toFixed(0)} % de la variación`,
        nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: c.tenue } }),
      yAxis: Object.assign({}, c.eje, { type: 'value', scale: true,
        name: `componente 2 · ${(ve[1] * 100).toFixed(0)} %`,
        nameTextStyle: { color: c.tenue } }),
      toolbox: V.herramientas(c),
      dataZoom: [{ type: 'inside', xAxisIndex: 0, yAxisIndex: 0, zoomOnMouseWheel: 'ctrl',
                   moveOnMouseWheel: false }],
      legend: { data: ['resto', 'marcados'], left: 52, top: 0, textStyle: { color: c.tenue },
                itemWidth: 12, itemHeight: 8 },
      series: [
        { name: 'resto', type: 'scatter', data: normales, symbolSize: 4, large: true,
          itemStyle: { color: c.tenue, opacity: .35 } },
        { name: 'marcados', type: 'scatter', data: marcados, symbolSize: 9,
          itemStyle: { color: V.serie(3), borderColor: V.varCss('--panel'), borderWidth: 1.5 },
          z: 5 },
      ],
    }),
    pie: `${miles(normales.length)} tramos sin marcar y ${miles(marcados.length)} marcados por ` +
         `${d.detector}. Las dos componentes juntas explican el ${((ve[0] + ve[1]) * 100).toFixed(0)} % ` +
         'de la variación: lo que no entra ahí no se ve en este dibujo.',
  });
}

// ---------------------------------------------------------------- 5. correlación
function correlacion(d) {
  const f = d.correlacion.features;
  const celdas = [];
  d.correlacion.matriz.forEach((fila, i) =>
    fila.forEach((v, j) => celdas.push([j, i, v])));
  const corto = (n) => n.replace('__', ' · ');
  const alto = Math.max(420, Math.min(760, f.length * 9 + 150));

  Grafico.medida($('#g-correlacion'), {
    alto,
    opcion: (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 186, right: 18, top: 34, bottom: 12 },
      tooltip: Object.assign({}, c.tooltip, {
        formatter: (p) => `<b>${V.fmt(p.data[2], 2)}</b> de correlación<br>` +
                          `<span style="color:${c.tenue}">${corto(f[p.data[1]])}<br>${corto(f[p.data[0]])}</span>`,
      }),
      // Divergente: dos tonos con gris neutro en el cero, porque la correlación tiene signo.
      visualMap: {
        min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', top: 0,
        itemWidth: 12, itemHeight: 120, precision: 2,
        textStyle: { color: c.tenue, fontSize: 10 },
        inRange: { color: [V.serie(0), V.varCss('--fondo-2'), V.serie(3)] },
      },
      xAxis: { type: 'category', data: f, axisTick: { show: false },
               axisLine: { lineStyle: { color: c.borde } },
               axisLabel: { show: false } },
      yAxis: {
        type: 'category', data: f, inverse: true, axisTick: { show: false },
        axisLine: { lineStyle: { color: c.borde } },
        axisLabel: {
          fontSize: 9, interval: 0,
          // Conservadas en tinta plena; descartadas, tenues. Así el mapa explica el filtrado.
          formatter: (v, i) => (d.correlacion.conservadas[i] ? `{ok|${corto(v)}}` : `{no|${corto(v)}}`),
          rich: { ok: { color: c.tinta, fontWeight: 600, fontSize: 9 },
                  no: { color: c.tenue, opacity: .55, fontSize: 9 } },
        },
      },
      series: [{ type: 'heatmap', data: celdas, progressive: 2000,
                 emphasis: { itemStyle: { borderColor: V.varCss('--acento'), borderWidth: 1 } } }],
    }),
    pie: `${f.length} características antes del filtrado; sobreviven ` +
         `${d.correlacion.conservadas.filter(Boolean).length}, en negrita.`,
  });
}

iniciar();

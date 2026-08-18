/* Los cuatro cortes de análisis de una rama, dentro de la vista de fase del taller.
 *
 * ESTO VIVÍA EN UNA PANTALLA APARTE. Se mudó acá porque la separación tenía un costo concreto:
 * elegir la rama del otro lado obligaba a reconocerla en un desplegable, y una rama ahí es apenas
 * un texto — cinco de seis terminaban con la misma etiqueta. Más de la mitad de este archivo eran
 * líneas para compensar eso: nombres sin empates, la tira de la cadena, el `?nodo=`. Dentro del
 * taller el nodo ya está elegido sobre el mapa, que es donde una rama se ve como lo que es, y todo
 * eso sobra.
 *
 * No calcula nada: recibe lo que devuelve `/api/nodo/{clave}/analisis` y dibuja. La regla de «qué
 * tramo está marcado» la decide el backend preguntándosela al paquete de la tesis.
 */

window.Analisis = (function () {
  'use strict';

  const V = Grafico.paleta;
  const miles = (v) => Number(v).toLocaleString('es');
  const $ = (s, raiz) => (raiz || document).querySelector(s);

  /** El texto explicativo de cada corte. Va en el JS porque la pestaña se arma al vuelo.
   *  Depende del nodo: en eventos hay material que en detección todavía no existe. */
  const secciones = (d) => [
    ['coincidencia', '¿En qué coinciden los métodos?',
     'Es el argumento central del trabajo: como nadie etiquetó estos datos, <strong>el acuerdo entre ' +
     'métodos que piensan distinto reemplaza a la respuesta correcta que no existe</strong>. En la ' +
     'tabla de eventos eso vive comprimido en un «4/5». A la izquierda, cuántos tramos marcan de a ' +
     'pares; en la diagonal, cuántos marca cada uno por su cuenta. A la derecha, cuántos tramos junta ' +
     'cada nivel de acuerdo.'],
    ...(d.eventos ? [['acuerdo', '¿Es acuerdo, o es duración?',
     'La pregunta incómoda del corte anterior. Un evento largo abarca muchos tramos vecinos, y ' +
     'cuantos más tramos abarca, más chances tiene de que <em>algún</em> método haya marcado ' +
     'alguno — sin que dos métodos hayan coincidido nunca en el mismo tramo. Si los eventos de ' +
     '4 y 5 métodos resultan ser sistemáticamente los más largos, ese número estaría midiendo ' +
     'duración antes que consenso. <strong>Cada punto es un evento</strong>; la línea une la ' +
     'mediana de cada grupo.']] : []),
    ['puntajes', '¿Cómo reparte los puntajes cada método?',
     'Un panel por método, porque <strong>los puntajes no se comparan entre métodos</strong>: cada uno ' +
     'tiene su escala. Lo que sí se compara es la forma. La línea punteada es el corte de candidatos: ' +
     'todo lo que queda a su derecha es lo que ese método marca.'],
    ['dispersion', '¿Están realmente aislados los candidatos?',
     'Cada punto es un tramo, proyectado a dos dimensiones para poder verlo. Los marcados por el método ' +
     'elegido van resaltados. Si aparecen en el borde de la nube, el método está encontrando cosas ' +
     'efectivamente atípicas; si caen en el medio del montón, marca por algo que esta vista no muestra. ' +
     '<strong>La proyección es solo para mirar</strong>: no alimenta ninguna etapa y ningún número de ' +
     'la tesis depende de ella.'],
    ['desplazamiento', '¿Qué hace distinta a una candidata?',
     'Cuánto se corre la media de las candidatas respecto del resto de los tramos, en desvíos ' +
     'estándar, característica por característica. Es lo que va a mirar quien tenga que etiquetar: ' +
     'no <em>cuáles</em> son raras, sino <em>en qué</em> son raras. Lo calcula el paquete de la ' +
     'tesis con las mismas funciones que arman su reporte de feature-shift.'],
    ['correlacion', '¿Por qué se descartaron esas características?',
     'Cada celda es cuánto se mueven juntas dos características. Los bloques intensos fuera de la ' +
     'diagonal son familias que repiten información, y de cada una sobrevive una. Las conservadas van ' +
     'en negrita en los rótulos.'],
  ];

  /** Arma el armazón de la pestaña y dibuja los cuatro cortes. */
  function pintar(destino, d, alCambiarDetector) {
    destino.innerHTML = secciones(d).map(([id, titulo, texto]) => `
      <div class="corte">
        <h4 style="font-size:.95rem;margin:0 0 4px">${titulo}</h4>
        <p class="explica">${texto}</p>
        ${id === 'coincidencia' ? '<div class="resumen-grid" id="cifras" style="margin:0 0 12px"></div>' : ''}
        ${id === 'dispersion' ? `<div class="fila-sup"><span class="esp"></span>
           <label class="tenue" style="font-size:.8rem" for="sel-det">Método</label>
           <select id="sel-det">${d.detectores.map((x) =>
             `<option ${x === d.detector ? 'selected' : ''}>${x}</option>`).join('')}</select></div>` : ''}
        ${id === 'coincidencia'
          ? '<div class="duo"><div id="g-coincidencia"></div><div id="g-reparto"></div></div>'
          : `<div id="g-${id}"></div>`}
      </div>`).join('');

    cifras(d);
    coincidencia(d);
    reparto(d);
    if (d.eventos) acuerdoODuracion(d);
    puntajes(d);
    dispersion(d);
    desplazamiento(d);
    correlacion(d);
    $('#sel-det').addEventListener('change', (e) => alCambiarDetector(e.target.value));
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
      opcion: (c, altoReal) => {
        const A = altoReal || alto;
        const grid = [], xAxis = [], yAxis = [], series = [];
        const paso = (A - 40) / dets.length;
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

  // ---------------------------------------------------------------- acuerdo vs duración
  function acuerdoODuracion(d) {
    const pts = d.eventos.puntos;
    const grupos = Object.keys(d.eventos.por_acuerdo).map(Number).sort((a, b) => a - b);
    // Los dos ejes son discretos y 40 puntos se pisan: se separan a mano, con un corrimiento
    // estable derivado del id para que no salten al redibujar.
    const jitter = (id) => ((id * 2654435761) % 1000) / 1000 * 0.5 - 0.25;
    const medianas = grupos.map((k) => [k, d.eventos.por_acuerdo[k].mediana]);

    Grafico.medida($('#g-acuerdo'), {
      titulo: 'Tamaño del evento contra métodos que lo marcan',
      alto: 340,
      opcion: (c) => ({
        animation: false,
        textStyle: c.textStyle,
        grid: { left: 62, right: 26, top: 16, bottom: 52 },
        tooltip: Object.assign({}, c.tooltip, {
          formatter: (p) => (p.seriesIndex === 1
            ? `mediana de <b>${p.data[1]}</b> tramos con ${p.data[0]} métodos`
            : `<b>Evento ${p.data[2]}</b> · ${p.data[3]}<br>` +
              `<span style="color:${c.tenue}">${p.data[1]} tramos · ${Math.round(p.data[0])} métodos</span>`),
        }),
        // El mínimo tiene que ser entero: ECharts cuenta las marcas desde `min` de a `interval`,
        // así que con 0,5 caían en 0,5 · 1,5 · 2,5… y ningún grupo quedaba rotulado.
        xAxis: Object.assign({}, c.eje, { type: 'value', min: 0, max: grupos.length + 0.6,
          interval: 1, name: 'métodos que marcan el evento', nameLocation: 'middle', nameGap: 30,
          nameTextStyle: { color: c.tenue }, splitLine: { show: false },
          axisLabel: { color: c.tenue, formatter: (v) => (d.eventos.por_acuerdo[v]
            ? `${v}\n(${d.eventos.por_acuerdo[v].n})` : '') } }),
        yAxis: Object.assign({}, c.eje, { type: 'value', name: 'tramos que abarca',
          nameTextStyle: { color: c.tenue } }),
        series: [
          { type: 'scatter', symbolSize: 11,
            data: pts.map((p) => [p.detectores + jitter(p.id), p.ventanas, p.id, p.hoja]),
            itemStyle: { color: V.serie(0), opacity: .75,
                         borderColor: V.varCss('--panel'), borderWidth: 1 } },
          { type: 'line', data: medianas, symbol: 'circle', symbolSize: 9,
            lineStyle: { color: V.serie(3), width: 2 }, itemStyle: { color: V.serie(3) }, z: 4 },
        ],
      }),
      pie: 'Debajo de cada grupo, entre paréntesis, cuántos eventos lo componen: los grupos de 4 y ' +
           '5 métodos son chicos, así que su mediana se mueve fácil. Es una señal para mirar, no una medición.',
    });
  }

  // ---------------------------------------------------------------- desplazamiento de features
  function desplazamiento(d) {
    const s = d.desplazamiento;
    const corto = (n) => n.replace('__', ' · ');
    // De mayor a menor desvío, y con el mayor arriba: se lee de arriba abajo como un ranking.
    const orden = s.features.map((_, i) => i).reverse();
    Grafico.medida($('#g-desplazamiento'), {
      titulo: `Las ${s.features.length} características que más se corren`,
      alto: Math.max(300, s.features.length * 17 + 70),
      opcion: (c) => ({
        animation: false,
        textStyle: c.textStyle,
        grid: { left: 210, right: 40, top: 12, bottom: 40 },
        tooltip: Object.assign({}, c.tooltip, { trigger: 'item',
          formatter: (p) => {
            const i = orden[p.dataIndex];
            return `<b>${s.shift[i] > 0 ? '+' : ''}${V.fmt(s.shift[i], 2)}</b> desvíos estándar<br>` +
                   `<span style="color:${c.tenue}">${corto(s.features[i])} · familia ${s.familia[i]}</span>`;
          } }),
        xAxis: Object.assign({}, c.eje, { type: 'value',
          name: 'desvíos estándar respecto del resto de los tramos',
          nameLocation: 'middle', nameGap: 26, nameTextStyle: { color: c.tenue } }),
        yAxis: Object.assign({}, c.eje, { type: 'category',
          data: orden.map((i) => corto(s.features[i])),
          axisTick: { show: false }, splitLine: { show: false },
          axisLabel: { color: c.tenue, fontSize: 10, interval: 0 } }),
        series: [{
          type: 'bar', barMaxWidth: 11,
          // Dos tonos porque el signo importa: hacia arriba o hacia abajo de lo normal.
          data: orden.map((i) => ({ value: s.shift[i],
            itemStyle: { color: s.shift[i] >= 0 ? V.serie(3) : V.serie(0) } })),
        }],
      }),
      pie: `Calculado sobre las ${miles(s.n_candidatas)} candidatas de ${d.detector}, contra el resto. ` +
           'Positivo: la candidata tiene ese valor más alto que un tramo normal; negativo, más bajo.',
    });
  }

  return { pintar };
})();

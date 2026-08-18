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
  /** Cada corte: id, título, la línea que dice qué mirar, el porqué (plegado) y si es secundario.
   *
   *  Los títulos eran los cinco preguntas —«¿En qué coinciden los métodos?», «¿Es acuerdo, o es
   *  duración?»…—, que no es estilo sino una plantilla, y cada uno traía un párrafo editorializando
   *  antes del gráfico. La interfaz llegó a tener casi 2.000 palabras de prosa. Ahora el título
   *  nombra, la línea dice dónde mirar, y el porqué está para quien lo busque. */
  const secciones = (d) => [
    ['coincidencia', 'Coincidencia entre métodos',
     'La diagonal es cuántos marca cada uno solo; fuera de ella, cuántos comparten de a pares.',
     'Nadie etiquetó estos datos, así que no hay contra qué medir el acierto. Que métodos con ideas ' +
     'distintas de «raro» señalen el mismo tramo es lo que reemplaza a esa respuesta que no existe.'],
    ...(d.eventos ? [['acuerdo', 'Acuerdo, o duración',
     'Si los eventos de más métodos son también los más largos, el acuerdo puede ser un efecto del tamaño.',
     'Un evento largo abarca muchos tramos vecinos, y cuantos más abarca, más chances tiene de que ' +
     'algún método haya marcado alguno — sin que dos hayan coincidido nunca en el mismo tramo.']] : []),
    ['desplazamiento', 'Qué corre en una candidata',
     'Cuánto se aparta cada característica respecto del resto de los tramos, en desvíos estándar.',
     'Es lo que va a mirar quien tenga que etiquetar en la Etapa 2: no cuáles son raras, sino en qué ' +
     'lo son. Lo calcula el paquete de la tesis, con las funciones de su reporte de feature-shift.'],
    ['puntajes', 'Reparto de puntajes',
     'La línea punteada es el corte de candidatos: a su derecha, lo que ese método marca.',
     'Un panel por método porque los puntajes no se comparan entre sí: cada uno tiene su escala. Lo ' +
     'que sí se compara es la forma — una cola larga y separada distingue mejor que una campana.', true],
    ['dispersion', 'Los candidatos en el plano',
     'En el borde de la nube, el método encuentra algo atípico; en el medio, marca por otra cosa.',
     'La proyección a dos dimensiones es solo para mirar: no alimenta ninguna etapa, no se guarda y ' +
     'ningún número del trabajo depende de ella.', true],
  ];


  /** Arma el armazón de la pestaña y dibuja los cuatro cortes. */
  /** Un corte: título, explicación y el hueco donde va su gráfico. */
  const bloque = (d) => ([id, titulo, linea, porque]) => `
      <div class="corte">
        <h4 style="font-size:.95rem;margin:0 0 4px">${titulo}</h4>
        <p class="pista">${linea}</p>
        ${porque ? `<details class="saber-mas"><summary>Por qué</summary><p>${porque}</p></details>` : ''}
        ${id === 'coincidencia' ? '<div class="resumen-grid" id="cifras" style="margin:0 0 12px"></div>' : ''}
        ${id === 'dispersion' ? `<div class="fila-sup"><span class="esp"></span>
           <label class="tenue" style="font-size:.8rem" for="sel-det">Método</label>
           <select id="sel-det">${d.detectores.map((x) =>
             `<option ${x === d.detector ? 'selected' : ''}>${x}</option>`).join('')}</select></div>` : ''}
        ${id === 'coincidencia'
          ? '<div class="duo"><div id="g-coincidencia"></div><div id="g-reparto"></div></div>'
          : `<div id="g-${id}"></div>`}
      </div>`;

  function pintar(destino, d, alCambiarDetector) {
    const todas = secciones(d);
    const principales = todas.filter((x) => !x[4]);
    const secundarias = todas.filter((x) => x[4]);

    // Los secundarios van detrás de un pliegue. No es esconderlos: es decir cuáles son los que
    // sostienen el argumento. Con nueve gráficos del mismo peso no se distingue el que puede
    // refutar la tesis del que está para mirar.
    destino.innerHTML = principales.map(bloque(d)).join('')
      + (secundarias.length ? `<details class="corte plegado"><summary>Más cortes de esta rama
           <span class="tenue">(${secundarias.length})</span></summary>
           ${secundarias.map(bloque(d)).join('')}</details>` : '');

    cifras(d);
    coincidencia(d);
    reparto(d);
    if (d.eventos) acuerdoODuracion(d);
    puntajes(d);
    dispersion(d);
    desplazamiento(d);
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
      pie: 'Bigotes a 1,5 veces el rango intercuartílico: ' +
         dets.map((n) => `${n} ${d.puntajes[n].atipicos}`).join(' · ') + ' tramos fuera.',
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

  // ---------------------------------------------------------------- acuerdo vs duración
  function acuerdoODuracion(d) {
    const pts = d.eventos.puntos;
    const grupos = Object.keys(d.eventos.por_acuerdo).map(Number).sort((a, b) => a - b);
    // Los dos ejes son discretos y 40 puntos se pisan: se separan a mano, con un corrimiento
    // estable derivado del id para que no salten al redibujar.
    const jitter = (id) => ((id * 2654435761) % 1000) / 1000 * 0.5 - 0.25;
    const medianas = grupos.map((k) => [k, d.eventos.por_acuerdo[k].mediana]);

    // Guiar es señalar dentro del dibujo, no escribir un párrafo al lado. El salto se busca —el
    // mayor entre dos grupos consecutivos— para que la anotación siga siendo cierta en otra rama,
    // y solo se marca si es grande de verdad.
    let salto = null;
    for (let i = 1; i < medianas.length; i++) {
      const dif = medianas[i][1] - medianas[i - 1][1];
      if (dif > 2 && (!salto || dif > salto.dif)) salto = { dif, desde: medianas[i - 1], hasta: medianas[i] };
    }

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
            lineStyle: { color: V.serie(3), width: 2 }, itemStyle: { color: V.serie(3) }, z: 4,
            markArea: salto ? {
              silent: true,
              itemStyle: { color: V.serie(3), opacity: .07 },
              label: { show: true, position: 'insideTop', color: V.serie(3), fontSize: 11,
                       fontWeight: 600,
                       formatter: `la mediana salta de ${salto.desde[1]} a ${salto.hasta[1]} tramos` },
              data: [[{ xAxis: salto.desde[0] }, { xAxis: grupos[grupos.length - 1] + 0.6 }]],
            } : undefined },
        ],
      }),
      pie: 'Entre paréntesis, cuántos eventos tiene cada grupo. Los de 4 y 5 métodos son chicos: ' +
           'su mediana se mueve fácil.',
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

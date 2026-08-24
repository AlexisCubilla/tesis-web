/* Motor de gráficos del taller, sobre ECharts.
 *
 * ECharts está versionado en `web/vendor/` (ver el LEEME de ahí): sin CDN, sin `npm install` y sin
 * paso de compilación, así que el ADR A6 sigue en pie — pasó de «sin dependencias» a «una
 * dependencia congelada en el repositorio».
 *
 * ESTE ARCHIVO ES EL ÚNICO QUE CONOCE ECHARTS. Todo lo demás (`app.js`, `analisis.js`) pide
 * gráficos por su nombre y le pasa datos. Si algún día hay que cambiar de librería, se cambia acá.
 *
 * LO QUE NO CAMBIÓ AL CAMBIAR DE LIBRERÍA. Las decisiones de la versión anterior se conservan
 * porque no eran de la implementación sino del contenido:
 *
 *   - Paneles apilados, nunca curvas superpuestas con escalas distintas. Tres señales con unidades
 *     distintas encimadas es un gráfico de dos ejes con los ejes escondidos.
 *   - Un solo eje X compartido y un solo zoom para todos los paneles.
 *   - La rueda del mouse no se secuestra: hace falta Ctrl para hacer zoom con ella, así que la
 *     página se sigue desplazando como en cualquier otro lado.
 *   - Los colores salen de las variables CSS, y se vuelven a leer al cambiar de tema.
 */

window.Grafico = (function () {
  'use strict';

  const vivos = new Set();
  const varCss = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const serie = (i) => varCss(`--serie-${(i % 5) + 1}`);

  /** La unidad suele venir dentro del nombre de la señal: «Vbat (V)» → «V». */
  function partirNombre(nombre) {
    const m = /^(.*?)\s*[（(]\s*([^)）]*)\s*[)）]\s*$/.exec(nombre || '');
    return m ? { nombre: m[1].trim(), unidad: m[2].trim() } : { nombre: nombre || '', unidad: '' };
  }

  const fmt = (v, d = 2) => (v == null || !isFinite(v))
    ? '—' : Number(v).toLocaleString('es', { maximumFractionDigits: d });

  /** Lo que toda opción comparte: tipografías, colores de eje y caja del globo, según el tema. */
  function comun() {
    const tinta = varCss('--texto'), tenue = varCss('--texto-2'), borde = varCss('--borde');
    return {
      tinta, tenue, borde,
      textStyle: { fontFamily: 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif',
                   color: tinta, fontSize: 11 },
      tooltip: {
        backgroundColor: varCss('--panel'), borderColor: borde, borderWidth: 1,
        textStyle: { color: tinta, fontSize: 12 }, extraCssText: 'box-shadow:' + varCss('--sombra'),
      },
      eje: {
        axisLine: { lineStyle: { color: borde } },
        axisTick: { lineStyle: { color: borde } },
        axisLabel: { color: tenue },
        splitLine: { lineStyle: { color: borde, opacity: .55 } },
      },
    };
  }

  /* ------------------------------------------------------------------ envoltura
     Un gráfico es un <div>, una instancia de ECharts y una función que arma la opción. Guardar la
     función —y no la opción ya armada— es lo que permite rehacerla con los colores nuevos cuando
     se cambia de tema, sin volver a pedirle nada al backend. */
  class Grafo {
    constructor(destino, cfg) {
      this.cfg = cfg;
      this.raiz = document.createElement('div');
      this.raiz.className = 'grafico';
      destino.appendChild(this.raiz);

      const compacto = !!cfg.compacto;
      if (!compacto && (cfg.titulo || cfg.acciones !== false)) {
        const b = document.createElement('div');
        b.className = 'grafico-acciones';
        if (cfg.titulo) {
          const t = document.createElement('h5');
          t.className = 'grafico-titulo';
          t.textContent = cfg.titulo;          // textContent: los nombres vienen del backend
          b.appendChild(t);
        }
        const esp = document.createElement('span');
        esp.className = 'esp';
        b.appendChild(esp);
        // Los iconos de ECharts van dentro del lienzo y son chicos; agrandar es una acción
        // frecuente y merece un botón con su nombre escrito.
        if (cfg.acciones !== false && !cfg.enModal) {
          const x = document.createElement('button');
          x.type = 'button';
          x.className = 'grafico-btn';
          x.textContent = '⤢ Agrandar';
          x.title = 'Abrir el gráfico en grande';
          x.addEventListener('click', () => this._agrandar());
          b.appendChild(x);
        }
        this.barra = b;
        this.raiz.appendChild(b);
      }

      this.caja = document.createElement('div');
      this.caja.className = 'grafico-caja';
      this.caja.style.height = (cfg.alto || 300) + 'px';
      this.raiz.appendChild(this.caja);


      if (cfg.pie && !compacto) {
        const p = document.createElement('p');
        p.className = 'grafico-pie';
        p.textContent = cfg.pie;
        this.raiz.appendChild(p);
      }

      this.eco = echarts.init(this.caja, null, { renderer: 'canvas' });

      // El botón va después de `init`: ECharts vacía el contenedor al inicializarse, así que si se
      // agrega antes desaparece en silencio. En las miniaturas no entra una botonera, pero
      // agrandar sigue haciendo falta —justamente porque son chicas—, así que va en la esquina.
      // Al abrirse se muestran como gráfico completo: ahí sí hay lugar para ejes y herramientas.
      if (compacto && !cfg.enModal) {
        const x = document.createElement('button');
        x.type = 'button';
        x.className = 'grafico-btn grafico-lupa';
        x.textContent = '⤢';
        x.title = 'Abrir el gráfico en grande';
        x.setAttribute('aria-label', 'Abrir el gráfico en grande');
        x.addEventListener('click', () => this._agrandar());
        this.caja.appendChild(x);
      }

      this.pintar();
      this.ro = new ResizeObserver(() => this.eco.resize());
      this.ro.observe(this.caja);
      vivos.add(this);
    }

    pintar() {
      // `notMerge`: al cambiar de tema hay que reemplazar la opción entera, no fusionarla, o
      // quedan mezclados los colores viejos con los nuevos.
      this.eco.setOption(this.cfg.opcion(comun(), this.cfg.alto || 300, !!this.cfg.enModal), true);
    }

    /** Abre una copia del mismo gráfico a pantalla casi completa. */
    _agrandar() {
      const dlg = document.createElement('dialog');
      dlg.className = 'grafico-modal';

      const cab = document.createElement('div');
      cab.className = 'grafico-acciones';
      const t = document.createElement('h5');
      t.className = 'grafico-titulo';
      t.textContent = this.cfg.titulo || 'Gráfico';
      const esp = document.createElement('span');
      esp.className = 'esp';
      const cerrar = document.createElement('button');
      cerrar.type = 'button';
      cerrar.className = 'grafico-btn';
      cerrar.textContent = '✕ Cerrar';
      cerrar.addEventListener('click', () => dlg.close());
      cab.append(t, esp, cerrar);

      const hueco = document.createElement('div');
      dlg.append(cab, hueco);
      document.body.appendChild(dlg);

      const grande = new Grafo(hueco, Object.assign({}, this.cfg, {
        titulo: null, enModal: true, compacto: false,
        alto: Math.max(this.cfg.alto || 300, window.innerHeight - 190),
      }));
      dlg.addEventListener('close', () => { grande.destruir(); dlg.remove(); });
      dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
      dlg.showModal();
      // El <dialog> recién tiene tamaño después de abrirse.
      requestAnimationFrame(() => grande.eco.resize());
    }

    destruir() {
      if (this.ro) this.ro.disconnect();
      this.eco.dispose();
      vivos.delete(this);
    }
  }

  /* ------------------------------------------------------------------ herramientas
     `dataZoom` de caja (arrastrar un rectángulo), volver al rango completo, ver los datos en una
     tabla y guardar la imagen. Lo que antes estaba escrito a mano, con mejor terminación. */
  function herramientas(c, tabla) {
    return {
      right: 6, top: 0, itemSize: 13, itemGap: 9,
      iconStyle: { borderColor: c.tenue },
      emphasis: { iconStyle: { borderColor: varCss('--acento') } },
      feature: {
        dataZoom: { title: { zoom: 'Acercar un tramo', back: 'Deshacer' }, yAxisIndex: 'none' },
        restore: { title: 'Ver todo' },
        dataView: { title: 'Ver los datos', lang: ['Datos', 'Cerrar', 'Actualizar'], readOnly: true,
                    backgroundColor: varCss('--panel'), textColor: c.tinta,
                    buttonColor: varCss('--acento-hondo'),
                    // Sin `optionToContent`, ECharts vuelca una serie abajo de la otra y el índice
                    // de medición se repite una vez por señal: 246 líneas para 79 mediciones. Lo
                    // que hace falta es una fila por medición y una columna por señal.
                    optionToContent: tabla },
        saveAsImage: { title: 'Guardar imagen', name: 'grafico', pixelRatio: 2,
                       backgroundColor: varCss('--panel') },
      },
    };
  }


  /* ------------------------------------------------------------------ tabla de datos
     Una fila por punto del eje X y una columna por panel. Es lo que hay que construir a mano:
     ECharts, librado a su criterio, escribe una serie abajo de la otra, así que el índice de
     medición aparece repetido una vez por señal y la tabla deja de poder leerse de corrido. */
  const escapar = (t) => String(t).replace(/[&<>"]/g, (ch) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));

  function tablaDePaneles(paneles, n, fx, xNombre) {
    const TOPE = 2000;
    return (opt) => {
      // Se respeta el acercamiento: `dataZoom` guarda el rango visible en porcentaje.
      let i0 = 0, i1 = n - 1;
      const dz = (opt.dataZoom || []).find((z) => z.start != null);
      if (dz && n > 1) {
        i0 = Math.max(0, Math.round((dz.start / 100) * (n - 1)));
        i1 = Math.min(n - 1, Math.round((dz.end / 100) * (n - 1)));
      }
      const paso = Math.max(1, Math.ceil((i1 - i0 + 1) / TOPE));

      const enc = [xNombre, ...paneles.map((p) => {
        const { nombre, unidad } = partirNombre(p.nombre);
        return unidad ? `${nombre} (${unidad})` : nombre;
      })];
      const filas = [];
      for (let i = i0; i <= i1; i += paso) {
        filas.push('<tr><td>' + escapar(fx(i)) + '</td>' +
          paneles.map((p) => '<td class="num">' + escapar(fmt(p.valores[i], 4)) + '</td>').join('') +
          '</tr>');
      }
      const aviso = paso > 1
        ? `<p class="grafico-pie">Se lista 1 de cada ${paso} filas (${filas.length} de ${i1 - i0 + 1}). Acercá el gráfico para verlas todas.</p>`
        : '';
      return '<div class="grafico-tabla tabla-scroll"><table><thead><tr>'
        + enc.map((h) => '<th>' + escapar(h) + '</th>').join('')
        + '</tr></thead><tbody>' + filas.join('') + '</tbody></table></div>' + aviso;
    };
  }

  /* ================================================================== líneas apiladas */
  function lineas(destino, cfg) {
    const paneles = (cfg.paneles || []).filter(Boolean);
    const n = Math.max(...paneles.map((p) => p.valores.length), 0);
    const fx = cfg.formatoX || ((i) => String(i));
    const compacto = !!cfg.compacto;
    const altoPanel = cfg.altoPanel || (compacto ? 70 : 110);
    const alto = paneles.length * altoPanel + (compacto ? 34 : 78);

    const opcion = (c, altoReal, enModal) => {
      const A = altoReal || alto;
      // Dentro del modal hay lugar de sobra: la miniatura se muestra como gráfico completo.
      const comp = compacto && !enModal;
      const arriba = comp ? 16 : 30;
      const abajo = comp ? 20 : 62;   // sitio para la barra de rango
      const util = A - arriba - abajo;
      const paso = util / paneles.length;

      const grid = [], xAxis = [], yAxis = [], series = [];
      paneles.forEach((p, i) => {
        const { nombre, unidad } = partirNombre(p.nombre);
        grid.push({ left: 58, right: 18, top: arriba + i * paso, height: paso - 22 });
        xAxis.push(Object.assign({}, c.eje, {
          type: 'category', gridIndex: i,
          data: Array.from({ length: n }, (_, k) => fx(k)),
          axisLabel: { show: i === paneles.length - 1, color: c.tenue },
          axisTick: { show: i === paneles.length - 1, lineStyle: { color: c.borde } },
          splitLine: { show: false },
          boundaryGap: false,
        }));
        yAxis.push(Object.assign({}, c.eje, {
          type: 'value', gridIndex: i, scale: true,
          name: unidad ? `${nombre}  ${unidad}` : nombre,
          nameLocation: 'end', nameGap: 7,
          nameTextStyle: { color: c.tinta, fontSize: 11, fontWeight: 600, align: 'left' },
          axisLine: { show: false }, axisTick: { show: false },
          splitNumber: Math.max(2, Math.round((paso - 22) / 32)),
          axisLabel: { color: c.tenue, hideOverlap: true, formatter: (v) => fmt(v, 3) },
        }));
        series.push({
          type: 'line', name: nombre, xAxisIndex: i, yAxisIndex: i,
          data: p.valores, showSymbol: false, symbolSize: 5,
          lineStyle: { width: 2, color: p.color || serie(i) },
          itemStyle: { color: p.color || serie(i) },
          connectNulls: false, sampling: 'lttb',
          emphasis: { focus: 'none' },
        });
      });

      const o = {
        animation: false,
        textStyle: c.textStyle,
        grid, xAxis, yAxis, series,
        // Un solo puntero para todos los paneles y un solo globo con todas las señales: nunca hay
        // que apuntarle a la línea.
        // El puntero y la barra de rango son CHROME del gráfico, no una acción
        // primaria ni una selección, así que no llevan el acento: si el acento
        // apareciera acá dejaría de significar «algo pasa en este lugar». Van con
        // la tinta tenue y con el filete, que es lo que corresponde a un control
        // de encuadre. De paso desaparece el riesgo de confundir el acento con
        // una de las cinco series, que comparten familia de matiz con él.
        axisPointer: { link: [{ xAxisIndex: 'all' }], label: { backgroundColor: varCss('--panel-2') } },
        tooltip: Object.assign({}, c.tooltip, {
          trigger: 'axis',
          axisPointer: { type: 'cross', crossStyle: { color: c.tenue }, lineStyle: { color: c.tenue } },
        }),
      };
      if (!comp) {
        o.toolbox = herramientas(c, tablaDePaneles(paneles, n, fx, cfg.xNombre || 'x'));
        o.dataZoom = [
          // Sin zoom con la rueda salvo que se tenga Ctrl apretado: si no, el gráfico se queda
          // con el desplazamiento de la página, que es lo que la persona estaba haciendo.
          { type: 'inside', xAxisIndex: 'all', zoomOnMouseWheel: 'ctrl', moveOnMouseWheel: false,
            moveOnMouseMove: true },
          // `moveHandleStyle` y `selectedDataBackground` van explícitos porque ECharts
          // trae celestes por defecto ahí (#d2dbee y #8fb0f7) y son los únicos colores
          // del sitio que no salen de la paleta: 2746 px de celeste medidos en una
          // captura de esta misma barra. No se veían mientras el sitio era azul.
          { type: 'slider', xAxisIndex: 'all', bottom: 8, height: 20,
            borderColor: c.borde, fillerColor: varCss('--fila-hover'),
            handleStyle: { color: c.tenue },
            moveHandleStyle: { color: c.borde },
            dataBackground: { lineStyle: { color: c.borde }, areaStyle: { color: c.borde } },
            selectedDataBackground: { lineStyle: { color: c.tenue }, areaStyle: { color: c.borde } },
            textStyle: { color: c.tenue, fontSize: 10 } },
        ];
      }
      return o;
    };

    // El pie y el título se arman siempre: el marco los oculta mientras es miniatura y los
    // muestra al abrirse en grande.
    const pie = `${n} ${cfg.sustantivo || 'puntos'}. Para acercarte a un tramo: arrastrá los `
      + 'extremos de la barra de abajo, o usá la lupa de la esquina y encerrá el tramo en un recuadro.';
    return new Grafo(destino, { titulo: cfg.titulo, alto, opcion, pie, compacto });
  }

  /* ================================================================== barras horizontales
     Horizontales porque las categorías son nombres largos: en vertical no hay dónde escribirlos. */
  function barras(destino, cfg) {
    const datos = (cfg.datos || []).filter((d) => isFinite(d.valor));
    const alto = Math.max(140, datos.length * 22 + 40);
    const opcion = (c) => ({
      animation: false,
      textStyle: c.textStyle,
      grid: { left: 8, right: 56, top: 8, bottom: 8, containLabel: true },
      tooltip: Object.assign({}, c.tooltip, { trigger: 'item',
        formatter: (p) => `<b>${fmt(p.value)}</b> · ${p.name}` }),
      xAxis: Object.assign({}, c.eje, { type: 'value', splitLine: { show: false }, axisLabel: { show: false } }),
      yAxis: Object.assign({}, c.eje, {
        type: 'category', inverse: true,
        data: datos.map((d) => d.etiqueta),
        axisLine: { show: false }, axisTick: { show: false },
        axisLabel: { color: c.tenue, width: 130, overflow: 'truncate' },
      }),
      series: [{
        type: 'bar', data: datos.map((d) => d.valor), barMaxWidth: 15,
        // `--grafico-unico` y no `serie(0)`: acá no hay una primera categoría de
        // cinco, hay una sola magnitud. Ver la nota de la ficha en `estilos.css`.
        itemStyle: { color: varCss('--grafico-unico'), borderRadius: [0, 5, 5, 0] },
        label: { show: true, position: 'right', color: c.tinta, fontFamily: 'ui-monospace, monospace',
                 fontSize: 11, formatter: (p) => fmt(p.value) },
      }],
    });
    return new Grafo(destino, { titulo: cfg.titulo, alto, opcion, pie: cfg.nota, acciones: false });
  }

  // Los gráficos se pintan sobre <canvas> y no heredan las variables CSS: al cambiar de tema hay
  // que rehacerlos. Se hace acá, sin volver a pedirle los datos al backend.
  addEventListener('tema-cambiado', () => vivos.forEach((g) => g.pintar()));

  return {
    lineas,
    barras,
    /** Escotilla para gráficos a medida (la pantalla de análisis): recibe la opción ya armada. */
    medida: (destino, cfg) => new Grafo(destino, cfg),
    paleta: { serie, varCss, comun, herramientas, fmt },
    /** Antes de reemplazar el contenido de un contenedor, para no dejar instancias colgando. */
    limpiar(destino) {
      for (const g of [...vivos]) {
        if (!destino || destino.contains(g.raiz) || !document.contains(g.raiz)) g.destruir();
      }
    },
  };
})();

/* Motor de gráficos del taller.
 *
 * Sin dependencias ni compilación: Canvas y DOM a mano (ADR A6). Reemplaza a los dibujos que había
 * antes, que eran líneas sueltas sin ejes — bonitos, pero no se podía leer ni un valor.
 *
 * DECISIONES QUE NO SON DE GUSTO
 *
 * 1. PANELES APILADOS, NO CURVAS SUPERPUESTAS. Antes las tres señales iban encimadas en un mismo
 *    dibujo, cada una escalada a su propio mínimo y máximo. Eso es un gráfico de dos ejes con los
 *    ejes escondidos: las alturas relativas mienten y no hay forma de saberlo mirando. Acá cada
 *    señal tiene su propio panel con su propia escala rotulada, y todos comparten el eje X. Se
 *    siguen comparando las formas —que es para lo que servía— pero ahora además se leen los
 *    valores, con su unidad.
 *
 * 2. UN SOLO ZOOM PARA TODOS LOS PANELES. Comparten el eje X, así que arrastrar sobre cualquiera
 *    recorta a todos. Si cada uno se moviera por su lado dejarían de ser comparables, que es lo
 *    único que justifica apilarlos.
 *
 * 3. EL ZOOM MUESTRA MÁS DATO, NO MÁS PÍXELES. Por eso el backend dejó de submuestrear la serie a
 *    300 puntos: acercarse sobre una curva diezmada solo agranda la diezma. Ver `get_datos`.
 *
 * 4. LA RUEDA DEL MOUSE NO SE SECUESTRA. Hacer zoom con la rueda rompe el desplazamiento de la
 *    página, que es lo que la persona estaba haciendo. Se arrastra para elegir un tramo, y se
 *    vuelve con un botón o doble clic.
 */

window.Grafico = (function () {
  'use strict';

  const vivos = new Set();

  const varCss = (n) => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
  const colorSerie = (i) => varCss(`--serie-${(i % 5) + 1}`);

  /** Cuántos decimales tiene sentido mostrar para un rango dado. */
  function decimales(rango) {
    if (!isFinite(rango) || rango === 0) return 2;
    const m = Math.log10(Math.abs(rango));
    if (m >= 3) return 0;
    if (m >= 1) return 1;
    if (m >= -1) return 2;
    return Math.min(5, Math.ceil(-m) + 1);
  }

  const fmt = (v, dec) => (v == null || !isFinite(v))
    ? '—'
    : v.toLocaleString('es', { minimumFractionDigits: dec, maximumFractionDigits: dec });

  /** Marcas de eje en números redondos: 1, 2, 2,5 o 5 por una potencia de diez. */
  function marcas(min, max, n) {
    if (!isFinite(min) || !isFinite(max)) return [];
    if (min === max) return [min];
    const bruto = (max - min) / Math.max(1, n);
    const mag = Math.pow(10, Math.floor(Math.log10(bruto)));
    const k = bruto / mag;
    const paso = (k <= 1 ? 1 : k <= 2 ? 2 : k <= 2.5 ? 2.5 : k <= 5 ? 5 : 10) * mag;
    const salida = [];
    for (let v = Math.ceil(min / paso) * paso; v <= max + paso * 1e-9; v += paso) {
      salida.push(Math.abs(v) < paso * 1e-9 ? 0 : v);
    }
    return salida;
  }

  /** La unidad suele venir dentro del nombre de la señal: «Vbat (V)» → «V». */
  function partirNombre(nombre) {
    const m = /^(.*?)\s*[（(]\s*([^)）]*)\s*[)）]\s*$/.exec(nombre || '');
    return m ? { nombre: m[1].trim(), unidad: m[2].trim() } : { nombre: nombre || '', unidad: '' };
  }

  const MI = 56, MD = 14, ALTO_TIT = 18, ALTO_EJEX = 26, SEP = 12;

  class Lineas {
    constructor(destino, cfg) {
      // `compacto`: miniaturas de 50 puntos dentro de una tarjeta. Conservan el globo con los
      // valores —que es lo que hacía falta— pero sin botonera, sin pie y sin zoom: acercarse a un
      // tramo de 50 mediciones no aporta nada y la caja es demasiado chica para la barra.
      this.cfg = Object.assign({ altoPanel: 96, xNombre: 'medición', acciones: true }, cfg);
      if (this.cfg.compacto) this.cfg.acciones = false;
      this.paneles = this.cfg.paneles.filter(Boolean);
      this.n = Math.max(...this.paneles.map((p) => p.valores.length), 0);
      this.i0 = 0;
      this.i1 = Math.max(0, this.n - 1);
      this.hover = null;
      this.arrastre = null;

      this.raiz = document.createElement('div');
      this.raiz.className = 'grafico';
      destino.appendChild(this.raiz);

      if (this.cfg.acciones) this._barra();

      this.caja = document.createElement('div');
      this.caja.className = 'grafico-caja';
      this.raiz.appendChild(this.caja);

      this.lienzo = document.createElement('canvas');
      this.lienzo.className = 'grafico-lienzo';
      this.lienzo.setAttribute('role', 'img');
      this.lienzo.setAttribute('aria-label', this._resumenAccesible());
      this.caja.appendChild(this.lienzo);

      this.globo = document.createElement('div');
      this.globo.className = 'grafico-globo';
      this.globo.hidden = true;
      this.caja.appendChild(this.globo);

      if (!this.cfg.compacto) {
        this.pie = document.createElement('p');
        this.pie.className = 'grafico-pie';
        this.raiz.appendChild(this.pie);
      }

      this._eventos();
      this.ro = new ResizeObserver(() => this.dibujar());
      this.ro.observe(this.caja);
      vivos.add(this);
      this.dibujar();
    }

    _resumenAccesible() {
      const nombres = this.paneles.map((p) => partirNombre(p.nombre).nombre).join(', ');
      return `Gráfico de líneas con ${this.paneles.length} panel(es): ${nombres}. ` +
             `${this.n} ${this.cfg.sustantivo || 'puntos'}. Los valores están en la tabla que abre el botón «Datos».`;
    }

    _barra() {
      const b = document.createElement('div');
      b.className = 'grafico-acciones';
      if (this.cfg.titulo) {
        const t = document.createElement('h5');
        t.className = 'grafico-titulo';
        t.textContent = this.cfg.titulo;      // textContent: los nombres vienen del backend
        b.appendChild(t);
      }
      const esp = document.createElement('span');
      esp.className = 'esp';
      b.appendChild(esp);

      const boton = (txt, tit, fn) => {
        const x = document.createElement('button');
        x.type = 'button';
        x.className = 'grafico-btn';
        x.textContent = txt;
        x.title = tit;
        x.addEventListener('click', fn);
        b.appendChild(x);
        return x;
      };
      this.btnVerTodo = boton('⟲ Ver todo', 'Volver al rango completo', () => this.restablecer());
      this.btnVerTodo.hidden = true;
      this.btnDatos = boton('Datos', 'Ver los valores en una tabla', () => this._alternarTabla());
      if (!this.cfg.enModal) boton('⤢ Agrandar', 'Abrir en grande', () => this._agrandar());
      this.raiz.appendChild(b);
    }

    // ---------------------------------------------------------------- geometría
    _medidas() {
      const an = this.caja.clientWidth || 600;
      const altoP = this.cfg.altoPanel;
      const al = this.paneles.length * altoP + (this.paneles.length - 1) * SEP + ALTO_EJEX;
      return { an, al, altoP, x0: MI, x1: Math.max(MI + 10, an - MD) };
    }

    _panelRect(i, m) {
      const arriba = i * (m.altoP + SEP);
      return { y0: arriba + ALTO_TIT, y1: arriba + m.altoP, tit: arriba };
    }

    _rango(p) {
      let mn = Infinity, mx = -Infinity;
      for (let i = this.i0; i <= this.i1; i++) {
        const v = p.valores[i];
        if (v == null || !isFinite(v)) continue;
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      if (mn === Infinity) return { mn: 0, mx: 1, plano: true };
      if (mn === mx) return { mn: mn - 1, mx: mx + 1, plano: true };
      const holgura = (mx - mn) * 0.08;
      return { mn: mn - holgura, mx: mx + holgura, plano: false };
    }

    _xDe(i, m) {
      const span = Math.max(1, this.i1 - this.i0);
      return m.x0 + ((i - this.i0) / span) * (m.x1 - m.x0);
    }

    _iDe(px, m) {
      const span = Math.max(1, this.i1 - this.i0);
      const i = this.i0 + ((px - m.x0) / Math.max(1, m.x1 - m.x0)) * span;
      return Math.max(this.i0, Math.min(this.i1, Math.round(i)));
    }

    // ---------------------------------------------------------------- dibujo
    dibujar() {
      if (!document.contains(this.lienzo)) return this.destruir();
      const m = this._medidas();
      const dpr = Math.min(3, window.devicePixelRatio || 1);
      this.lienzo.width = Math.round(m.an * dpr);
      this.lienzo.height = Math.round(m.al * dpr);
      this.lienzo.style.height = m.al + 'px';
      const c = this.lienzo.getContext('2d');
      c.setTransform(dpr, 0, 0, dpr, 0, 0);
      c.clearRect(0, 0, m.an, m.al);

      const tinta = varCss('--texto'), tenue = varCss('--texto-2'), reja = varCss('--borde');
      c.font = '10px system-ui, sans-serif';
      c.textBaseline = 'middle';

      this.paneles.forEach((p, pi) => {
        const r = this._panelRect(pi, m);
        const rg = this._rango(p);
        p._rg = rg; p._r = r;
        const yDe = (v) => r.y1 - ((v - rg.mn) / (rg.mx - rg.mn)) * (r.y1 - r.y0);

        // título del panel y unidad
        const { nombre, unidad } = partirNombre(p.nombre);
        c.fillStyle = tinta; c.textAlign = 'left';
        c.fillText(nombre, m.x0, r.tit + ALTO_TIT / 2);
        if (unidad) {
          const w = c.measureText(nombre).width;
          c.fillStyle = tenue;
          c.fillText(` ${unidad}`, m.x0 + w + 4, r.tit + ALTO_TIT / 2);
        }

        // Rejilla y rótulos del eje Y, recesivos y por detrás del dato. La cantidad de divisiones
        // sale de la altura disponible, y además se saltea el rótulo que caería pegado al anterior:
        // los paneles chicos (los cinco detectores, las miniaturas) no tienen sitio para cuatro
        // números de 10 px y quedaban amontonados unos sobre otros.
        const dec = decimales(rg.mx - rg.mn);
        const alto = r.y1 - r.y0;
        const divs = Math.max(2, Math.min(4, Math.round(alto / 30)));
        // Pedir pocas divisiones no garantiza pocas marcas: garantiza un paso grande, y con ciertos
        // rangos ese paso deja UNA sola marca, que no alcanza para leer una escala. Se sube la
        // exigencia hasta conseguir al menos tres; el salteo de abajo se ocupa de que no choquen.
        let ticks = marcas(rg.mn, rg.mx, divs);
        for (let k = divs + 1; ticks.length < 3 && k <= 8; k++) ticks = marcas(rg.mn, rg.mx, k);
        c.lineWidth = 1; c.textAlign = 'right';
        let ultimaY = Infinity;
        for (const v of ticks) {
          const y = Math.round(yDe(v)) + .5;
          if (y < r.y0 - 1 || y > r.y1 + 1) continue;
          c.strokeStyle = reja;
          c.beginPath(); c.moveTo(m.x0, y); c.lineTo(m.x1, y); c.stroke();
          if (ultimaY - y < 13) continue;
          ultimaY = y;
          c.fillStyle = tenue;
          c.fillText(fmt(v, dec), m.x0 - 8, y);
        }

        // la línea
        c.strokeStyle = p.color || colorSerie(pi);
        c.lineWidth = 2; c.lineJoin = 'round'; c.lineCap = 'round';
        c.beginPath();
        let trazando = false;
        for (let i = this.i0; i <= this.i1; i++) {
          const v = p.valores[i];
          if (v == null || !isFinite(v)) { trazando = false; continue; }
          const x = this._xDe(i, m), y = yDe(v);
          trazando ? c.lineTo(x, y) : c.moveTo(x, y);
          trazando = true;
        }
        c.stroke();

        // Con pocos puntos la línea sola engaña: se marca cada medición.
        if (this.i1 - this.i0 <= 60) {
          c.fillStyle = p.color || colorSerie(pi);
          for (let i = this.i0; i <= this.i1; i++) {
            const v = p.valores[i];
            if (v == null || !isFinite(v)) continue;
            c.beginPath(); c.arc(this._xDe(i, m), yDe(v), 2.2, 0, 6.2832); c.fill();
          }
        }
      });

      // eje X compartido
      const yEje = m.al - ALTO_EJEX + 6;
      c.strokeStyle = reja; c.lineWidth = 1;
      c.beginPath(); c.moveTo(m.x0, yEje - 6.5); c.lineTo(m.x1, yEje - 6.5); c.stroke();
      c.fillStyle = tenue; c.textAlign = 'center';
      const fx = this.cfg.formatoX || ((i) => String(i));
      for (const i of marcas(this.i0, this.i1, 6)) {
        const ii = Math.round(i);
        if (ii < this.i0 || ii > this.i1) continue;
        c.fillText(fx(ii), this._xDe(ii, m), yEje + 5);
      }
      c.textAlign = 'right';
      c.fillText(this.cfg.xNombre, m.x1, yEje + 16);

      if (this.arrastre) this._pintarSeleccion(c, m);
      if (this.hover != null) this._pintarCruz(c, m);
      this._pintarPie();
    }

    _pintarSeleccion(c, m) {
      const a = Math.min(this.arrastre.a, this.arrastre.b);
      const b = Math.max(this.arrastre.a, this.arrastre.b);
      c.fillStyle = varCss('--acento') + '2e';
      c.fillRect(a, 0, b - a, m.al - ALTO_EJEX);
      c.strokeStyle = varCss('--acento'); c.lineWidth = 1;
      c.beginPath();
      c.moveTo(a + .5, 0); c.lineTo(a + .5, m.al - ALTO_EJEX);
      c.moveTo(b - .5, 0); c.lineTo(b - .5, m.al - ALTO_EJEX);
      c.stroke();
    }

    _pintarCruz(c, m) {
      const x = Math.round(this._xDe(this.hover, m)) + .5;
      c.strokeStyle = varCss('--texto-2'); c.lineWidth = 1;
      c.setLineDash([3, 3]);
      c.beginPath(); c.moveTo(x, 0); c.lineTo(x, m.al - ALTO_EJEX); c.stroke();
      c.setLineDash([]);
      this.paneles.forEach((p) => {
        const v = p.valores[this.hover];
        if (v == null || !isFinite(v)) return;
        const y = p._r.y1 - ((v - p._rg.mn) / (p._rg.mx - p._rg.mn)) * (p._r.y1 - p._r.y0);
        c.fillStyle = varCss('--panel');
        c.beginPath(); c.arc(x, y, 4.5, 0, 6.2832); c.fill();
        c.strokeStyle = p.color || colorSerie(this.paneles.indexOf(p));
        c.lineWidth = 2; c.stroke();
      });
    }

    _pintarPie() {
      if (!this.pie) return;
      const zoom = this.i0 > 0 || this.i1 < this.n - 1;
      if (this.btnVerTodo) this.btnVerTodo.hidden = !zoom;
      const total = this.i1 - this.i0 + 1;
      const q = this.cfg.sustantivo || 'puntos';
      this.pie.textContent = zoom
        ? `Mostrando ${total} de ${this.n} ${q} (${this.i0}–${this.i1}). Arrastrá para acercar más, doble clic para volver.`
        : `${this.n} ${q}. Arrastrá sobre el gráfico para acercar un tramo.`;
    }

    // ---------------------------------------------------------------- interacción
    _eventos() {
      const pos = (e) => {
        const r = this.lienzo.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
      };

      this.lienzo.addEventListener('pointermove', (e) => {
        const m = this._medidas(), p = pos(e);
        if (this.arrastre) {
          this.arrastre.b = Math.max(m.x0, Math.min(m.x1, p.x));
          this.hover = null;
          this.globo.hidden = true;
          return this.dibujar();
        }
        if (p.x < m.x0 - 6 || p.x > m.x1 + 6) { this._salir(); return; }
        this.hover = this._iDe(p.x, m);
        this._globo(p);
        this.dibujar();
      });

      this.lienzo.addEventListener('pointerleave', () => this._salir());

      this.lienzo.addEventListener('pointerdown', (e) => {
        if (e.button !== 0 || this.cfg.compacto) return;
        const m = this._medidas(), p = pos(e);
        const x = Math.max(m.x0, Math.min(m.x1, p.x));
        this.arrastre = { a: x, b: x };
        this.lienzo.setPointerCapture(e.pointerId);
      });

      this.lienzo.addEventListener('pointerup', (e) => {
        if (!this.arrastre) return;
        const m = this._medidas();
        const { a, b } = this.arrastre;
        this.arrastre = null;
        if (Math.abs(b - a) >= 10) {
          const ia = this._iDe(Math.min(a, b), m), ib = this._iDe(Math.max(a, b), m);
          if (ib - ia >= 2) { this.i0 = ia; this.i1 = ib; }
        }
        try { this.lienzo.releasePointerCapture(e.pointerId); } catch { /* ya soltado */ }
        this.dibujar();
      });

      if (!this.cfg.compacto) this.lienzo.addEventListener('dblclick', () => this.restablecer());
    }

    _salir() {
      this.hover = null;
      this.globo.hidden = true;
      this.dibujar();
    }

    /** Un globo con TODOS los paneles a la vez: no hay que apuntarle a la línea. */
    _globo(p) {
      const i = this.hover;
      this.globo.replaceChildren();

      const cab = document.createElement('div');
      cab.className = 'g-cab';
      cab.textContent = `${this.cfg.xNombre} ${(this.cfg.formatoX || String)(i)}`;
      this.globo.appendChild(cab);

      this.paneles.forEach((pa, pi) => {
        const v = pa.valores[i];
        const { nombre, unidad } = partirNombre(pa.nombre);
        const fila = document.createElement('div');
        fila.className = 'g-fila';
        const llave = document.createElement('span');
        llave.className = 'g-llave';
        llave.style.background = pa.color || colorSerie(pi);
        const val = document.createElement('b');
        val.textContent = fmt(v, decimales(pa._rg ? pa._rg.mx - pa._rg.mn : 1)) + (unidad ? ' ' + unidad : '');
        const nom = document.createElement('span');
        nom.className = 'g-nom';
        nom.textContent = nombre;
        fila.append(llave, val, nom);
        this.globo.appendChild(fila);
      });

      this.globo.hidden = false;
      const an = this.caja.clientWidth;
      const ancho = this.globo.offsetWidth;
      const izq = p.x + 14 + ancho > an ? p.x - 14 - ancho : p.x + 14;
      this.globo.style.left = Math.max(0, izq) + 'px';
      this.globo.style.top = Math.max(0, Math.min(p.y + 12, this.lienzo.clientHeight - this.globo.offsetHeight)) + 'px';
    }

    restablecer() {
      this.i0 = 0;
      this.i1 = Math.max(0, this.n - 1);
      this.dibujar();
    }

    // ---------------------------------------------------------------- tabla y modal
    _alternarTabla() {
      if (this.tabla) { this.tabla.remove(); this.tabla = null; return; }
      const TOPE = 300;
      const total = this.i1 - this.i0 + 1;
      const paso = Math.max(1, Math.ceil(total / TOPE));
      const cont = document.createElement('div');
      cont.className = 'grafico-tabla tabla-scroll';
      const t = document.createElement('table');
      const thead = document.createElement('thead');
      const trh = document.createElement('tr');
      [this.cfg.xNombre, ...this.paneles.map((p) => p.nombre)].forEach((h) => {
        const th = document.createElement('th');
        th.textContent = h;
        trh.appendChild(th);
      });
      thead.appendChild(trh);
      const tb = document.createElement('tbody');
      for (let i = this.i0; i <= this.i1; i += paso) {
        const tr = document.createElement('tr');
        const td0 = document.createElement('td');
        td0.textContent = (this.cfg.formatoX || String)(i);
        tr.appendChild(td0);
        this.paneles.forEach((pa) => {
          const td = document.createElement('td');
          td.className = 'num';
          td.textContent = fmt(pa.valores[i], decimales(pa._rg ? pa._rg.mx - pa._rg.mn : 1));
          tr.appendChild(td);
        });
        tb.appendChild(tr);
      }
      t.append(thead, tb);
      cont.appendChild(t);
      if (paso > 1) {
        // Nada de recortes silenciosos: si la tabla no muestra todo, lo dice.
        const n = document.createElement('p');
        n.className = 'grafico-pie';
        n.textContent = `Se lista 1 de cada ${paso} mediciones (${Math.ceil(total / paso)} de ${total}). Acercá el gráfico para verlas todas.`;
        cont.appendChild(n);
      }
      this.raiz.appendChild(cont);
      this.tabla = cont;
    }

    _agrandar() {
      const dlg = document.createElement('dialog');
      dlg.className = 'grafico-modal';
      const cerrar = document.createElement('button');
      cerrar.type = 'button';
      cerrar.className = 'grafico-btn grafico-cerrar';
      cerrar.textContent = '✕ Cerrar';
      cerrar.addEventListener('click', () => dlg.close());
      const hueco = document.createElement('div');
      dlg.append(cerrar, hueco);
      document.body.appendChild(dlg);

      const grande = new Lineas(hueco, Object.assign({}, this.cfg, {
        altoPanel: Math.max(150, Math.round((window.innerHeight - 190) / this.paneles.length) - SEP),
        enModal: true,
      }));
      grande.i0 = this.i0; grande.i1 = this.i1; grande.dibujar();

      dlg.addEventListener('close', () => { grande.destruir(); dlg.remove(); });
      dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });
      dlg.showModal();
      requestAnimationFrame(() => grande.dibujar());
    }

    destruir() {
      if (this.ro) this.ro.disconnect();
      vivos.delete(this);
    }
  }

  /* ------------------------------------------------------------------ barras
     En HTML, no en Canvas: los rótulos quedan nítidos y seleccionables, cada barra es su propio
     blanco de hover sin cuentas de píxeles, y desaparece el problema que tenía la versión anterior
     — nombres rotados y cortados a 13 caracteres para que entraran. Horizontales porque las
     categorías son nombres largos: en vertical no hay dónde escribirlos. */
  function barras(destino, cfg) {
    const datos = (cfg.datos || []).filter((d) => isFinite(d.valor));
    const raiz = document.createElement('div');
    raiz.className = 'grafico';
    if (cfg.titulo) {
      const t = document.createElement('h5');
      t.className = 'grafico-titulo';
      t.textContent = cfg.titulo;
      raiz.appendChild(t);
    }
    const lista = document.createElement('div');
    lista.className = 'barras';
    const max = Math.max(...datos.map((d) => d.valor), 1);
    const dec = decimales(max);
    datos.forEach((d) => {
      const fila = document.createElement('div');
      fila.className = 'barra-fila';
      fila.tabIndex = 0;
      const et = document.createElement('span');
      et.className = 'barra-et';
      et.textContent = d.etiqueta;             // textContent: viene del backend
      et.title = d.etiqueta;
      const pista = document.createElement('span');
      pista.className = 'barra-pista';
      const rell = document.createElement('span');
      rell.className = 'barra-rell';
      rell.style.width = (d.valor / max * 100).toFixed(2) + '%';
      pista.appendChild(rell);
      const val = document.createElement('span');
      val.className = 'barra-val';
      val.textContent = fmt(d.valor, dec);
      fila.append(et, pista, val);
      fila.setAttribute('aria-label', `${d.etiqueta}: ${fmt(d.valor, dec)}`);
      lista.appendChild(fila);
    });
    raiz.appendChild(lista);
    if (cfg.nota) {
      const n = document.createElement('p');
      n.className = 'grafico-pie';
      n.textContent = cfg.nota;
      raiz.appendChild(n);
    }
    destino.appendChild(raiz);
    return raiz;
  }

  // Los <canvas> se pintan a mano y no heredan las variables CSS: al cambiar de tema hay que
  // redibujar. Se hace acá, sin volver a pedir los datos al backend.
  addEventListener('tema-cambiado', () => vivos.forEach((g) => g.dibujar()));

  return {
    lineas: (destino, cfg) => new Lineas(destino, cfg),
    barras,
    /** Antes de reemplazar el contenido de un contenedor, para no dejar ResizeObservers colgando.
     *  Sin argumento limpia todo; con uno, solo lo que cuelga de ahí (y lo ya desprendido). */
    limpiar(destino) {
      for (const g of [...vivos]) {
        if (!destino || destino.contains(g.raiz) || !document.contains(g.raiz)) g.destruir();
      }
    },
  };
})();

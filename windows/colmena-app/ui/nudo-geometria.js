// Geometría pura del nudo (sin canvas ni Tauri): la usan nudo.html y ui-pruebas/.
// Puntos como [x, y] en coordenadas lógicas del monitor; monitor = { ancho, alto }.
(function (raiz) {
  const distancia = (a, b) => Math.hypot(b[0] - a[0], b[1] - a[1]);

  function acotar(p, m, margen) {
    return [
      Math.min(Math.max(p[0], margen), m.ancho - margen),
      Math.min(Math.max(p[1], margen), m.alto - margen),
    ];
  }

  // Punto del rectángulo más cercano a o (o mismo si está adentro).
  function cercano(o, r) {
    return [Math.min(Math.max(o[0], r.x), r.x + r.ancho), Math.min(Math.max(o[1], r.y), r.y + r.alto)];
  }

  function interpolar(a, b, t) {
    return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
  }

  function puntoCurva(p0, c, p1, t) {
    const u = 1 - t;
    return [u * u * p0[0] + 2 * u * t * c[0] + t * t * p1[0], u * u * p0[1] + 2 * u * t * c[1] + t * t * p1[1]];
  }

  // Control de una curva cuadrática que se arquea hacia adentro de la pantalla.
  // Como la curva queda dentro del triángulo p0-c-p1, con los extremos en pantalla
  // y c acotado al monitor, toda la trayectoria queda en pantalla.
  function controlCurva(p0, p1, m, margen = 12) {
    const dx = p1[0] - p0[0];
    const dy = p1[1] - p0[1];
    const largo = Math.hypot(dx, dy);
    const medio = interpolar(p0, p1, 0.5);
    if (largo < 1) return acotar(medio, m, margen);
    const k = Math.min(0.22 * largo, 240);
    const n = [-dy / largo, dx / largo];
    const centro = [m.ancho / 2, m.alto / 2];
    let mejor = null;
    for (const s of [1, -1]) {
      const c = [medio[0] + n[0] * k * s, medio[1] + n[1] * k * s];
      const dentro = acotar(c, m, margen);
      const sobra = distancia(c, dentro);
      const alCentro = distancia(c, centro);
      if (!mejor || sobra < mejor.sobra - 1e-9 || (Math.abs(sobra - mejor.sobra) <= 1e-9 && alCentro < mejor.alCentro)) {
        mejor = { c: dentro, sobra, alCentro };
      }
    }
    return mejor.c;
  }

  // Dónde flota la abejita: pegada al borde del objetivo que mira hacia `desde`.
  function posAbejita(r, desde, m, { separacion = 20, margen = 16 } = {}) {
    const q = cercano(desde, r);
    const d = distancia(q, desde);
    if (d > 1e-6) {
      const p = [q[0] + ((desde[0] - q[0]) / d) * separacion, q[1] + ((desde[1] - q[1]) / d) * separacion];
      return acotar(p, m, margen);
    }
    // `desde` cae dentro del objetivo: el lado libre más cercano.
    const cx = r.x + r.ancho / 2;
    const cy = r.y + r.alto / 2;
    const lados = [
      [cx, r.y - separacion],
      [cx, r.y + r.alto + separacion],
      [r.x - separacion, cy],
      [r.x + r.ancho + separacion, cy],
    ];
    const caben = lados.filter((p) => distancia(p, acotar(p, m, margen)) < 1e-9);
    const opciones = caben.length ? caben : lados;
    opciones.sort((a, b) => distancia(a, desde) - distancia(b, desde));
    return acotar(opciones[0], m, margen);
  }

  // cubic-bezier(0.2, 0, 0, 1): salida suave, arranca rápido y se posa despacio.
  function suave(x) {
    if (x <= 0) return 0;
    if (x >= 1) return 1;
    const bx = (s) => 3 * (1 - s) * (1 - s) * s * 0.2 + s * s * s;
    let lo = 0;
    let hi = 1;
    for (let i = 0; i < 24; i++) {
      const s = (lo + hi) / 2;
      if (bx(s) < x) lo = s;
      else hi = s;
    }
    const s = (lo + hi) / 2;
    return 3 * (1 - s) * s * s + s * s * s;
  }

  function duracionVuelo(p0, p1) {
    return Math.min(800, 600 + Math.max(0, distancia(p0, p1) - 150) * 0.15);
  }

  function masCercano(o, objetivos) {
    let mejor = -1;
    let dMin = Infinity;
    objetivos.forEach((obj, i) => {
      const d = distancia(o, cercano(o, obj.rect));
      if (d < dMin) {
        dMin = d;
        mejor = i;
      }
    });
    return mejor;
  }

  // Al limpiar el dibujo la abejita no desaparece de golpe: hace un tramo hacia el reloj mientras se desvanece.
  const TRAMO_SALIDA = 0.3;

  function salidaAbejita(desde, origen, k) {
    const t = Math.min(Math.max(k, 0), 1);
    return { p: interpolar(desde, origen, suave(t) * TRAMO_SALIDA), alfa: 1 - t };
  }

  const NudoGeo = {
    acotar,
    cercano,
    interpolar,
    puntoCurva,
    controlCurva,
    posAbejita,
    suave,
    duracionVuelo,
    masCercano,
    salidaAbejita,
  };
  if (typeof module === 'object' && module.exports) module.exports = NudoGeo;
  else raiz.NudoGeo = NudoGeo;
})(typeof window !== 'undefined' ? window : globalThis);

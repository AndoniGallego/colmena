// Pruebas de la geometría del nudo: node --test windows/colmena-app/ui-pruebas/
// Fuera de ui/ para que no se empaqueten con la app.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const G = require('../ui/nudo-geometria.js');

const MONITOR = { ancho: 1920, alto: 1080 };
const ORIGEN = [1880, 1040];
const MARGEN = 12;
const CASOS = {
  'borde derecho': { x: 1800, y: 500, ancho: 120, alto: 40 },
  'arriba a la derecha': { x: 1700, y: 0, ancho: 220, alto: 30 },
  'abajo a la izquierda': { x: 0, y: 1050, ancho: 200, alto: 30 },
  'arriba a la izquierda': { x: 0, y: 0, ancho: 60, alto: 24 },
};

const dentro = (p, m, margen = 0) =>
  p[0] >= margen - 1e-9 && p[0] <= m.ancho - margen + 1e-9 && p[1] >= margen - 1e-9 && p[1] <= m.alto - margen + 1e-9;

function distanciaARect(p, r) {
  const dx = Math.max(r.x - p[0], 0, p[0] - (r.x + r.ancho));
  const dy = Math.max(r.y - p[1], 0, p[1] - (r.y + r.alto));
  return Math.hypot(dx, dy);
}

for (const [nombre, rect] of Object.entries(CASOS)) {
  test(`el control de la curva queda dentro del monitor: ${nombre}`, () => {
    const p1 = G.cercano(ORIGEN, rect);
    const c = G.controlCurva(ORIGEN, p1, MONITOR, MARGEN);
    assert.ok(dentro(c, MONITOR, MARGEN), `control fuera: ${c}`);
  });

  test(`toda la trayectoria queda dentro del monitor: ${nombre}`, () => {
    const destino = G.posAbejita(rect, ORIGEN, MONITOR);
    const c = G.controlCurva(ORIGEN, destino, MONITOR, MARGEN);
    for (let i = 0; i <= 50; i++) {
      const q = G.puntoCurva(ORIGEN, c, destino, i / 50);
      assert.ok(dentro(q, MONITOR), `punto fuera en t=${i / 50}: ${q}`);
    }
  });

  test(`la abejita queda pegada al objetivo y dentro del monitor: ${nombre}`, () => {
    const p = G.posAbejita(rect, ORIGEN, MONITOR);
    assert.ok(dentro(p, MONITOR, 16), `abejita fuera: ${p}`);
    const d = distanciaARect(p, rect);
    assert.ok(d <= 20 + 1e-6 && d >= 18, `abejita lejos o encima del objetivo: ${d}`);
  });
}

test('la curva sigue siendo curva lejos de los bordes', () => {
  const p0 = [400, 800];
  const p1 = [1400, 300];
  const c = G.controlCurva(p0, p1, MONITOR, MARGEN);
  const medio = G.interpolar(p0, p1, 0.5);
  assert.ok(Math.hypot(c[0] - medio[0], c[1] - medio[1]) > 50);
});

test('el control apunta hacia adentro de la pantalla (origen en la esquina, objetivo arriba)', () => {
  const p1 = [1880, 30];
  const c = G.controlCurva(ORIGEN, p1, MONITOR, MARGEN);
  assert.ok(c[0] < 1880, `debería curvarse hacia la izquierda: ${c}`);
});

test('la abejita con el origen dentro del objetivo igual queda pegada y en pantalla', () => {
  const rect = { x: 1700, y: 900, ancho: 220, alto: 180 };
  const p = G.posAbejita(rect, ORIGEN, MONITOR);
  assert.ok(dentro(p, MONITOR, 16));
  assert.ok(distanciaARect(p, rect) <= 20 + 1e-6);
});

test('interpolar en t=0 y t=1 da los extremos', () => {
  assert.deepEqual(G.interpolar([10, 20], [110, -80], 0), [10, 20]);
  assert.deepEqual(G.interpolar([10, 20], [110, -80], 1), [110, -80]);
  assert.deepEqual(G.interpolar([0, 0], [100, 50], 0.5), [50, 25]);
});

test('puntoCurva en t=0 y t=1 da los extremos', () => {
  const p0 = [5, 5];
  const p1 = [300, 200];
  assert.deepEqual(G.puntoCurva(p0, [100, 0], p1, 0), p0);
  assert.deepEqual(G.puntoCurva(p0, [100, 0], p1, 1), p1);
});

test('la curva de easing va de 0 a 1, crece y arranca rápido', () => {
  assert.equal(G.suave(0), 0);
  assert.equal(G.suave(1), 1);
  let antes = 0;
  for (let i = 1; i <= 20; i++) {
    const v = G.suave(i / 20);
    assert.ok(v >= antes - 1e-9);
    antes = v;
  }
  assert.ok(G.suave(0.5) > 0.8, 'cubic-bezier(0.2,0,0,1) pasa el 80% a mitad de camino');
});

test('el vuelo dura entre 600 y 800 ms', () => {
  assert.equal(G.duracionVuelo([0, 0], [10, 0]), 600);
  assert.equal(G.duracionVuelo([0, 0], [3000, 0]), 800);
  const m = G.duracionVuelo([1880, 1040], [900, 500]);
  assert.ok(m > 600 && m < 800);
});

test('elige el objetivo más cercano al origen', () => {
  const objetivos = [{ rect: CASOS['abajo a la izquierda'] }, { rect: CASOS['borde derecho'] }];
  assert.equal(G.masCercano(ORIGEN, objetivos), 1);
  assert.equal(G.masCercano(ORIGEN, []), -1);
});

test('al salir, la abejita arranca donde estaba y entera', () => {
  const s = G.salidaAbejita([500, 400], ORIGEN, 0);
  assert.deepEqual(s.p, [500, 400]);
  assert.equal(s.alfa, 1);
});

test('al salir, la abejita se acerca al reloj sin llegar y se desvanece del todo', () => {
  const desde = [500, 400];
  const fin = G.salidaAbejita(desde, ORIGEN, 1);
  assert.equal(fin.alfa, 0);
  const antes = Math.hypot(ORIGEN[0] - desde[0], ORIGEN[1] - desde[1]);
  const despues = Math.hypot(ORIGEN[0] - fin.p[0], ORIGEN[1] - fin.p[1]);
  assert.ok(despues < antes, 'se acerca al reloj');
  assert.ok(despues > 0, 'no vuela todo el camino: se desvanece antes');
});

test('al salir, el avance se acota entre 0 y 1', () => {
  assert.deepEqual(G.salidaAbejita([10, 10], ORIGEN, -3), G.salidaAbejita([10, 10], ORIGEN, 0));
  assert.deepEqual(G.salidaAbejita([10, 10], ORIGEN, 7), G.salidaAbejita([10, 10], ORIGEN, 1));
});

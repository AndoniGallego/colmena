import { describe, expect, it } from 'vitest'
import { clavesDeLineas, nuevoCacheAnsi, nuevoReusoClaves, palette, parseAnsi, parseAnsiLineas } from './ansi'

const text = (ls: ReturnType<typeof parseAnsi>) => ls.map((l) => l.map((s) => s.t).join(''))

describe('parseAnsi', () => {
  it('separa líneas con \\r\\n y \\n', () => {
    expect(text(parseAnsi('uno\r\ndos\ntres'))).toEqual(['uno', 'dos', 'tres'])
  })
  it('aplica colores 16, 256 y 24 bits, negrita y reinicio', () => {
    const [l] = parseAnsi('\x1b[1;31mrojo\x1b[0m \x1b[38;5;196mx\x1b[38;2;10;20;30my\x1b[0m')
    expect(l[0]).toMatchObject({ t: 'rojo', b: true, fg: 'var(--ansi-1)' })
    expect(l[1].fg).toBeUndefined()
    expect(l[2]).toMatchObject({ t: 'x', fg: '#ff0000' })
    expect(l[3]).toMatchObject({ t: 'y', fg: '#0a141e' })
  })
  it('colores fuera de rango no rompen', () => {
    const [l] = parseAnsi('\x1b[38;5;999mz\x1b[38;2;999;0;5mw')
    expect(l[0].fg).toBe(palette(255))
    expect(l[1].fg).toMatch(/^#[0-9a-f]{6}$/)
  })
  it('inverso intercambia colores', () => {
    const [l] = parseAnsi('\x1b[31;7mx')
    expect(l[0]).toMatchObject({ fg: 'var(--term-bg)', bg: 'var(--ansi-1)' })
  })
  it('el retorno de carro sobrescribe la línea (barra de progreso)', () => {
    expect(text(parseAnsi('[#   ] 10%\r[##  ] 20%'))).toEqual(['[##  ] 20%'])
    expect(text(parseAnsi('abcdef\rXY'))).toEqual(['XYcdef'])
  })
  it('descarta OSC (8, 52, título) y CSI que no son SGR', () => {
    const out = text(parseAnsi('a\x1b]8;;javascript:alert(1)\x07link\x1b]8;;\x07\x1b]52;c;SGVsbG8=\x07b\x1b]0;titulo\x1b\\c\x1b[2J\x1b[Hd\x1b[?1049h\x1b(Be'))
    expect(out).toEqual(['alinkbcde'])
  })
  it('muestra bidi, ancho cero y C1 como ⟨U+XXXX⟩', () => {
    const [l] = parseAnsi('a‮b​c\u009B31m')
    const t = l.map((s) => s.t).join('')
    expect(t).toContain('⟨U+202E⟩')
    expect(t).toContain('⟨U+200B⟩')
    expect(t).toContain('⟨U+009B⟩')
    expect(t).not.toMatch(/[‮​\u009b]/)
  })
  it('expande tabs a columnas de 8', () => {
    expect(text(parseAnsi('ab\tc'))).toEqual(['ab      c'])
  })
  it('HTML queda como texto literal', () => {
    expect(text(parseAnsi('<script>alert(1)</script>'))).toEqual(['<script>alert(1)</script>'])
  })
  it('500 líneas con estilos en menos de 20 ms', () => {
    const big = Array.from({ length: 500 }, (_, i) => `\x1b[3${i % 8}mlínea ${i}\x1b[0m ${'x'.repeat(80)}`).join('\r\n')
    parseAnsi(big)
    let best = Infinity
    for (let k = 0; k < 7; k++) {
      const t0 = performance.now()
      expect(parseAnsi(big)).toHaveLength(500)
      best = Math.min(best, performance.now() - t0)
    }
    expect(best).toBeLessThan(20)
  })
  it('separadores de línea y párrafo Unicode se ven como código, no parten la línea', () => {
    expect(text(parseAnsi('a\u2028b\u2029c'))).toEqual(['a⟨U+2028⟩b⟨U+2029⟩c'])
  })
  it('secuencias cortadas al final no dejan basura ni rompen', () => {
    for (const cut of ['x\x1b', 'x\x1b[', 'x\x1b[38;2;', 'x\x1b[31', 'x\x1b]8;;http://e', 'x\x1bP1;2', 'x\x1b(']) {
      expect(text(parseAnsi(cut))).toEqual(['x'])
    }
  })
  it('parámetros SGR enormes o incompletos se ignoran', () => {
    const [l] = parseAnsi(`\x1b[${'9'.repeat(400)}mok\x1b[38;5mz\x1b[38;2;1my`)
    expect(l.map((s) => s.t).join('')).toBe('okzy')
    for (const sp of l) if (sp.fg) expect(sp.fg).toMatch(/^(#[0-9a-f]{6}|var\(--ansi-\d{1,2}\))$/)
  })
  it('los colores nunca llevan texto de la entrada', () => {
    const [l] = parseAnsi('\x1b[38;2;1;2;3;url(x)mz\x1b[38;5;1;expression(alert(1))mw')
    for (const sp of l) for (const v of [sp.fg, sp.bg]) if (v) expect(v).toMatch(/^(#[0-9a-f]{6}|var\(--ansi-\d{1,2}\)|var\(--term-(bg|fg)\))$/)
  })
  it('una entrada enorme de una sola línea se parsea sin colgarse', () => {
    const big = '\x1b[31m' + 'y'.repeat(256 * 1024)
    const t0 = performance.now()
    expect(parseAnsi(big)[0][0].t).toHaveLength(256 * 1024)
    expect(performance.now() - t0).toBeLessThan(1000)
  })
})


describe('parseAnsiLineas (memo por línea)', () => {
  const salidas = [
    'uno\ndos\ntres',
    'uno\ndos\ntres\n',
    '\x1b[31mrojo abierto\nsigue rojo\x1b[0m normal\notra',
    '\x1b[1;4;38;5;196mx\ny\n\x1b[22mz\x1b[0m\nw\x1b[7minv\nmas inv',
    'a\r\nb\x1b[42m verde\r\n\r\nc\td\x08e\u202e\x00',
    '\n\n',
    '',
    'x\n\x1b[0m',
  ]
  it.each(salidas.map((s, i) => [i, s] as const))('da lo mismo que parseAnsi (caso %i)', (_i, s) => {
    expect(parseAnsiLineas(s, nuevoCacheAnsi())).toEqual(parseAnsi(s))
  })
  it('un color abierto en una línea y cerrado en la siguiente sigue igual con caché tibia', () => {
    const c = nuevoCacheAnsi()
    parseAnsiLineas('\x1b[31mrojo\nsigue', c)
    expect(parseAnsiLineas('\x1b[31mrojo\nsigue', c)).toEqual(parseAnsi('\x1b[31mrojo\nsigue'))
    expect(parseAnsiLineas('sigue', c)).toEqual(parseAnsi('sigue'))
  })
  it('reutiliza el mismo objeto para las líneas que no cambiaron al correr la salida', () => {
    const c = nuevoCacheAnsi()
    const txt = (a: number) => Array.from({ length: 10 }, (_, k) => `\x1b[32mlinea ${a + k}\x1b[0m`).join('\n')
    const a = parseAnsiLineas(txt(0), c)
    const b = parseAnsiLineas(txt(3), c)
    expect(b[0]).toBe(a[3])
    expect(b[6]).toBe(a[9])
    expect(b[9]).not.toBe(a[9])
  })
  it('una secuencia abierta que cruza líneas cae al parseo completo', () => {
    const s = 'a\x1b]0;titulo\nresto\x07 fin\nz'
    expect(parseAnsiLineas(s, nuevoCacheAnsi())).toEqual(parseAnsi(s))
  })
  it('el caché no crece: solo conserva lo usado en la última pasada', () => {
    const c = nuevoCacheAnsi()
    parseAnsiLineas('a\nb\nc', c)
    parseAnsiLineas('d', c)
    expect(c.size).toBe(1)
  })
  it('líneas idénticas generan claves distintas y las claves son estables al correr la salida', () => {
    const c = nuevoCacheAnsi()
    const a = parseAnsiLineas('igual\nigual\notra', c)
    const ka = clavesDeLineas(a)
    expect(new Set(ka).size).toBe(3)
    const b = parseAnsiLineas('igual\notra\nnueva', c)
    const kb = clavesDeLineas(b)
    expect(kb[0]).toBe(ka[0])
    expect(kb[1]).toBe(ka[2])
  })
})

describe('nuevoReusoClaves', () => {
  it('las líneas nuevas heredan las claves de las que salieron y todas son únicas', () => {
    const reuso = nuevoReusoClaves()
    const a = reuso(['a.0', 'b.0', 'c.0', 'd.0'])
    const b = reuso(['c.0', 'd.0', 'e.0', 'f.0'])
    expect(b[0]).toBe(a[2])
    expect(b[1]).toBe(a[3])
    expect(new Set(b)).toEqual(new Set([a[2], a[3], a[0], a[1]]))
    const c = reuso(['x.0', 'y.0', 'z.0', 'w.0'])
    expect(new Set(c)).toEqual(new Set(b))
    const d = reuso(['x.0', 'y.0', 'z.0', 'w.0', 'v.0'])
    expect(new Set(d).size).toBe(5)
  })
  it('un contenido que reaparece no choca con la clave heredada por otra línea', () => {
    const reuso = nuevoReusoClaves()
    reuso(['a.0', 'b.0'])
    const b = reuso(['b.0', 'c.0'])
    const c = reuso(['b.0', 'c.0', 'a.0'])
    expect(new Set(c).size).toBe(3)
    expect(c[0]).toBe(b[0])
    expect(c[1]).toBe(b[1])
  })
})

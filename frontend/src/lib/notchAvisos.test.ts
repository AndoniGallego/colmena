import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { Aviso, AvisoKind } from '../api/types'
import {
  abrirSesionDesdeAvisoSimple,
  crearControlCierreDone,
  debeReemplazarAvisoActual,
  DURACION_TERMINO_S,
  BRILLO_AVISO_KIND,
  ETIQUETA_AVISO,
  brilloPillDesdeAviso,
  MAX_ESPERA_TERMINO_MS,
  maxId,
  msRestanteCierreDone,
  nombreAviso,
  nuevosParaNotch,
  siguienteAviso,
  type AvisoNotch,
  type KindNotch,
} from './notchAvisos'

const aviso = (id: number, kind: AvisoKind, over: Partial<Aviso> = {}): Aviso => ({
  id,
  ts: id,
  kind,
  titulo: `t${id}`,
  cuerpo: `c${id}`,
  session_id: 's',
  pane_id: '',
  fecha: '',
  mr: '',
  tag: '',
  entregado: true,
  leido: false,
  motivo: '',
  ...over,
})

const n = (id: number, kind: KindNotch, session_id: string): AvisoNotch => ({
  id,
  kind,
  titulo: '',
  cuerpo: '',
  session_id,
})

describe('lib/notchAvisos', () => {
  it('BRILLO_AVISO_KIND y brilloPillDesdeAviso', () => {
    expect(BRILLO_AVISO_KIND).toEqual({
      done: 'var(--st-done)',
      asks: 'var(--st-working)',
      blocked: 'var(--st-blocked)',
      pestana: 'var(--accent)',
    })
    const aviso = n(1, 'done', 's')
    expect(brilloPillDesdeAviso('ready', 'aviso', aviso)).toBe('var(--st-done)')
    expect(brilloPillDesdeAviso('ready', 'panel', aviso)).toBeNull()
    expect(brilloPillDesdeAviso('login', 'aviso', aviso)).toBeNull()
    expect(brilloPillDesdeAviso('ready', 'aviso', null)).toBeNull()
  })

  it('nombreAviso y ETIQUETA_AVISO', () => {
    expect(nombreAviso('Colmena terminó', 'done')).toBe('Colmena')
    expect(nombreAviso('Terminó Notch', 'done')).toBe('Terminó Notch')
    expect(nombreAviso(' terminó', 'done')).toBe(' terminó')
    expect(nombreAviso('Ana te pregunta', 'asks')).toBe('Ana')
    expect(nombreAviso('Algo espera una aprobación', 'blocked')).toBe('Algo')
    expect(ETIQUETA_AVISO.done).toBe('Terminó')
    expect(ETIQUETA_AVISO.asks).toBe('Te pregunta')
    expect(ETIQUETA_AVISO.blocked).toBe('Espera tu aprobación')
  })

  it('abrirSesionDesdeAvisoSimple: devuelve session_id o null', () => {
    expect(abrirSesionDesdeAvisoSimple('s-done')).toBe('s-done')
    expect(abrirSesionDesdeAvisoSimple('')).toBeNull()
    expect(abrirSesionDesdeAvisoSimple('   ')).toBeNull()
  })

  describe('crearControlCierreDone (soft)', () => {
    beforeEach(() => vi.useFakeTimers())
    afterEach(() => vi.useRealTimers())

    it('mouseenter a mitad: pasar más del total no cierra; mouseleave cierra tras el restante', () => {
      const cerrar = vi.fn()
      let now = 0
      const total = DURACION_TERMINO_S * 1000
      const ctrl = crearControlCierreDone({
        duracionMs: total,
        margenTimeoutMs: 0,
        now: () => now,
        onCerrar: cerrar,
        schedule: (fn, ms) => setTimeout(fn, ms),
        cancel: (id) => {
          if (id != null) clearTimeout(id)
        },
      })
      now = total / 2
      vi.advanceTimersByTime(total / 2)
      ctrl.pointerEnter()
      vi.advanceTimersByTime(total * 2)
      expect(cerrar).not.toHaveBeenCalled()
      ctrl.pointerLeave()
      vi.advanceTimersByTime(total / 2 - 1)
      expect(cerrar).not.toHaveBeenCalled()
      vi.advanceTimersByTime(2)
      expect(cerrar).toHaveBeenCalledTimes(1)
      ctrl.dispose()
    })
  })

  it('msRestanteCierreDone: cuenta hacia atrás y no pasa de cero', () => {
    const dur = DURACION_TERMINO_S * 1000
    const deadline = 10_000 + dur
    expect(msRestanteCierreDone(deadline, 10_000)).toBe(dur)
    expect(msRestanteCierreDone(deadline, 10_000 + dur / 2)).toBe(dur / 2)
    expect(msRestanteCierreDone(deadline, deadline)).toBe(0)
    expect(msRestanteCierreDone(deadline, deadline + 500)).toBe(0)
  })

  it('asks, blocked, done y pestana, y solo lo nuevo', () => {
    const items = [
      aviso(6, 'mr'),
      aviso(5, 'pestana', { pedido: '550e8400-e29b-41d4-a716-446655440000' }),
      aviso(4, 'done'),
      aviso(3, 'asks'),
      aviso(2, 'blocked'),
      aviso(1, 'asks'),
    ]
    expect(nuevosParaNotch(items, 2).map((a) => [a.id, a.kind])).toEqual([
      [3, 'asks'],
      [4, 'done'],
      [5, 'pestana'],
    ])
    expect(maxId(items)).toBe(6)
    expect(maxId([])).toBe(0)
  })

  it('siguienteAviso saltea te toca ya resueltos y prioriza te-toca sobre done', () => {
    const r = siguienteAviso(
      [n(1, 'asks', 'sx'), n(2, 'done', 'sy'), n(3, 'blocked', 'sz')],
      new Set(['sz']),
    )
    expect(r.aviso?.id).toBe(3)
    expect(r.resto.map((a) => a.id)).toEqual([2])
  })

  it('te-toca vigente pasa adelante de un done aunque el done llegó antes', () => {
    const cola = [n(1, 'done', 's1'), n(2, 'asks', 's2')]
    const r = siguienteAviso(cola, new Set(['s2']))
    expect(r.aviso?.id).toBe(2)
    expect(r.resto.map((a) => a.id)).toEqual([1])
  })

  it('descarta done si hay te-toca de la misma sesión en la cola', () => {
    const cola = [n(1, 'done', 's1'), n(2, 'asks', 's1')]
    const r = siguienteAviso(cola, new Set(['s1']))
    expect(r.aviso?.id).toBe(2)
    expect(r.resto.map((a) => a.id)).toEqual([])
    expect(r.descartados.map((a) => a.id)).toEqual([1])
  })

  it('descarta done si se está mostrando te-toca de la misma sesión', () => {
    const mostrando = n(9, 'blocked', 's1')
    const cola = [n(1, 'done', 's1')]
    const r = siguienteAviso(cola, new Set(['s1']), undefined, { mostrando })
    expect(r.aviso).toBeNull()
    expect(r.resto).toEqual([])
    expect(r.descartados.map((a) => a.id)).toEqual([1])
  })

  it('descarta done que esperó más de MAX_ESPERA_TERMINO_MS', () => {
    const ahora = 100_000
    const cola = [n(1, 'done', 's1')]
    const llegada = (a: AvisoNotch) => (a.id === 1 ? ahora - MAX_ESPERA_TERMINO_MS - 1 : undefined)
    const r = siguienteAviso(cola, new Set(), undefined, { ahora, llegada })
    expect(r.aviso).toBeNull()
    expect(r.descartados.map((a) => a.id)).toEqual([1])
  })

  it('entre done vigentes elige el de llegada más antigua', () => {
    const ahora = 50_000
    const cola = [n(3, 'done', 'a'), n(1, 'done', 'b')]
    const llegada = (a: AvisoNotch) => ({ 1: 49_000, 3: 49_500 }[a.id])
    const r = siguienteAviso(cola, new Set(), undefined, { ahora, llegada })
    expect(r.aviso?.id).toBe(1)
    expect(r.resto.map((a) => a.id)).toEqual([3])
  })

  it('debeReemplazarAvisoActual: done visible + te-toca vigente de la misma sesión', () => {
    const actual = n(1, 'done', 's1')
    const nuevos = [n(2, 'asks', 's1')]
    expect(debeReemplazarAvisoActual(actual, nuevos, new Set(['s1']))?.id).toBe(2)
  })

  it('debeReemplazarAvisoActual: done visible + te-toca de otra sesión no reemplaza', () => {
    const actual = n(1, 'done', 's1')
    const nuevos = [n(2, 'asks', 's2')]
    expect(debeReemplazarAvisoActual(actual, nuevos, new Set(['s2']))).toBeNull()
  })

  it('debeReemplazarAvisoActual: sin aviso visible o ya te-toca → null', () => {
    const nuevos = [n(2, 'asks', 's1')]
    expect(debeReemplazarAvisoActual(null, nuevos, new Set(['s1']))).toBeNull()
    expect(debeReemplazarAvisoActual(n(1, 'asks', 's1'), nuevos, new Set(['s1']))).toBeNull()
  })
})

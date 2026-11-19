import { describe, expect, it } from 'vitest'
import { correccionId, parteKey, reintentoId, toEnviado } from './enviado'
import { toConsultado } from './consultado'
const ID = 'aaaaaaaa-1111-4222-8333-444444444444'

describe('toEnviado', () => {
  it('un estado desconocido se muestra como incierto', () => {
    expect(toEnviado({ id: ID, texto: 'x', estado: 'raro' })!.estado).toBe('incierto')
    expect(toEnviado({ id: ID, texto: 'x', estado: 'error', detalle: 'falló' })).toMatchObject({ estado: 'error', detalle: 'falló' })
    expect(toEnviado({ texto: 'x' })).toBeNull()
  })
})

describe('toConsultado', () => {
  it('lee estado, motivo y detalle; un estado desconocido es incierto y sin id no hay tarjeta', () => {
    expect(toConsultado({ id: ID, pane_id: 'p1', destino: 'PS9', estado: 'rechazada', motivo: 'No le pregunté' })).toMatchObject({ estado: 'rechazada', motivo: 'No le pregunté' })
    expect(toConsultado({ id: ID, estado: 'raro' })!.estado).toBe('incierto')
    expect(toConsultado({ estado: 'ok' })).toBeNull()
  })
})

describe('ids de reintento y corrección', () => {
  it('son válidos para el servidor y distintos del original', () => {
    const ok = /^[A-Za-z0-9_-]{8,64}$/
    for (const id of [ID, 'x'.repeat(64)]) {
      expect(reintentoId(id)).toMatch(ok)
      expect(correccionId(id)).toMatch(ok)
      expect(reintentoId(id)).not.toBe(id)
    }
    expect(parteKey('m1', ID)).toBe(`m1:${ID}`)
  })
})

import { describe, expect, it } from 'vitest'
import { conteo, PRUEBAS_LIMITES, toPruebas } from './pruebas'
import { parseSegments } from './segments'

const caso = (o: Record<string, unknown> = {}) => ({ nombre: 'Login', resultado: 'ok', ...o })

describe('toPruebas', () => {
  it('acepta un informe válido', () => {
    const p = toPruebas({ titulo: 'Checkout', resumen: 'Todo bien', casos: [caso({ detalle: 'ok', evidencia: '/tmp/a.png' })] })
    expect(p).toEqual({ titulo: 'Checkout', resumen: 'Todo bien', casos: [{ nombre: 'Login', resultado: 'ok', detalle: 'ok', evidencia: '/tmp/a.png' }] })
  })
  it('normaliza el resultado y descarta casos inválidos', () => {
    const p = toPruebas({ titulo: 'T', casos: [caso({ resultado: ' FALLA ' }), caso({ resultado: 'rota' }), caso({ nombre: ' ' }), caso({ resultado: 'Omitida' })] })
    expect(p!.casos.map((c) => c.resultado)).toEqual(['falla', 'omitida'])
  })
  it('ignora evidencia que no es ruta absoluta', () => {
    const p = toPruebas({ titulo: 'T', casos: [caso({ evidencia: 'a.png' })] })
    expect(p!.casos[0]).not.toHaveProperty('evidencia')
  })
  it('acepta un ID de captura ss_… y rechaza basura', () => {
    expect(toPruebas({ titulo: 'T', casos: [caso({ evidencia: 'ss_1617g80dx' })] })!.casos[0].evidencia).toBe('ss_1617g80dx')
    for (const malo of ['ss_', 'ss_AB12', 'xx_abc123', 'ss_abc 123', 'ss_' + 'a'.repeat(41)]) {
      expect(toPruebas({ titulo: 'T', casos: [caso({ evidencia: malo })] })!.casos[0]).not.toHaveProperty('evidencia')
    }
  })
  it('recorta textos y limita a 60 casos', () => {
    const p = toPruebas({ titulo: 'x'.repeat(300), casos: Array.from({ length: 70 }, () => caso({ nombre: 'n'.repeat(500) })) })!
    expect(p.titulo.length).toBeLessThanOrEqual(PRUEBAS_LIMITES.titulo + 1)
    expect(p.casos).toHaveLength(PRUEBAS_LIMITES.casos)
    expect(p.casos[0].nombre.length).toBeLessThanOrEqual(PRUEBAS_LIMITES.nombre + 1)
  })
  it('devuelve null sin titulo, sin casos válidos o con basura', () => {
    expect(toPruebas({ casos: [caso()] })).toBeNull()
    expect(toPruebas({ titulo: 'T', casos: [caso({ resultado: 'x' })] })).toBeNull()
    expect(toPruebas(null)).toBeNull()
    expect(toPruebas([1])).toBeNull()
  })
})

describe('conteo', () => {
  it('cuenta por resultado', () => {
    const p = toPruebas({ titulo: 'T', casos: [caso(), caso(), caso({ resultado: 'falla' })] })!
    expect(conteo(p)).toEqual({ ok: 2, falla: 1, omitida: 0 })
  })
})

describe('parseSegments con pruebas', () => {
  it('convierte el bloque en tarjeta', () => {
    const segs = parseSegments('Listo\n\n```pruebas\n{"titulo":"T","casos":[{"nombre":"a","resultado":"ok"}]}\n```')
    expect(segs.map((s) => s.type)).toEqual(['md', 'pruebas'])
  })
  it('deja como markdown un bloque inválido', () => {
    expect(parseSegments('```pruebas\n{"titulo":"T","casos":[]}\n```').map((s) => s.type)).toEqual(['md'])
  })
})

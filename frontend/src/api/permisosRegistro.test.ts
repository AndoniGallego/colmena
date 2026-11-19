import { describe, expect, it } from 'vitest'
import { normalizePermisosRegistro } from './http'

describe('normalizePermisosRegistro', () => {
  it('conserva quien política o usuario', () => {
    const { items } = normalizePermisosRegistro({
      items: [
        { categoria: 'auto', quien: 'politica', herramienta: 'Bash' },
        { categoria: 'usuario', quien: 'usuario', herramienta: 'Edit' },
        { categoria: 'auto', quien: 'otro', herramienta: 'Read' },
      ],
    })
    expect(items).toHaveLength(3)
    expect(items[0].quien).toBe('politica')
    expect(items[1].quien).toBe('usuario')
    expect(items[2].quien).toBeUndefined()
  })

  it('campos nuevos y descartes inválidos', () => {
    const { items } = normalizePermisosRegistro({
      items: [
        {
          categoria: 'auto',
          quien: 'centinela',
          tool_use_id: 'tu-1',
          motivo_centinela: 'encargo urgente',
          encargo_id: 'enc-9',
          session_id: 's1',
          objecion: { nota: 'no me convence', hora: '2026-11-03T12:00:00Z' },
        },
        { categoria: 'auto', quien: 'centinela', tool_use_id: 9, objecion: { nota: 1 } },
        { categoria: 'auto', motivo_centinela: 123 },
        { categoria: 'nope', quien: 'centinela' },
      ],
    })
    expect(items).toHaveLength(3)
    expect(items[0]).toMatchObject({
      quien: 'centinela',
      tool_use_id: 'tu-1',
      motivo_centinela: 'encargo urgente',
      encargo_id: 'enc-9',
      objecion: { nota: 'no me convence', hora: '2026-11-03T12:00:00Z' },
    })
    expect(items[1].tool_use_id).toBeUndefined()
    expect(items[1].objecion).toBeUndefined()
    expect(items[2].motivo_centinela).toBeUndefined()
  })

  it('acepta filas con decision y sin categoria; descarta basura', () => {
    const { items } = normalizePermisosRegistro({
      items: [{ decision: 'rechazar', quien: 'usuario' }, { quien: 'x' }, 'basura', { decision: 'rara' }],
    })
    expect(items).toHaveLength(1)
    expect(items[0]).toMatchObject({ decision: 'rechazar', quien: 'usuario' })
    expect(items[0].categoria).toBeUndefined()
  })
})

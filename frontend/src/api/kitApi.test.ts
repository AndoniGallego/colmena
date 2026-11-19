import { describe, expect, it, vi } from 'vitest'
import { ApiError } from './types'
import { arreglarKit, getKit, getRegla, normalizarKit } from './kitApi'

const crudo = {
  estado: { al_dia: false, problemas: ['Falta instalar la regla «x».', 5] },
  reglas: [{ id: 'estado-sesion', titulo: 'Estado', proposito: 'Hace algo.' }, { titulo: 'sin id' }],
  skills: [{ id: 'diagramas', nombre: 'diagramas', que_hace: 'Dibuja.' }],
  hooks: [{ id: 'a.sh', nombre: 'a.sh', que_hace: 'Hook.' }],
}

describe('kitApi', () => {
  it('normaliza y descarta lo inválido', () => {
    const k = normalizarKit(crudo)
    expect(k.estado).toEqual({ al_dia: false, problemas: ['Falta instalar la regla «x».'] })
    expect(k.reglas).toEqual([{ id: 'estado-sesion', titulo: 'Estado', proposito: 'Hace algo.' }])
    expect(k.skills[0].que_hace).toBe('Dibuja.')
    expect(k.hooks).toHaveLength(1)
  })

  it('basura da un kit vacío y no al día', () => {
    expect(normalizarKit(null)).toEqual({ estado: { al_dia: false, problemas: [] }, reglas: [], skills: [], hooks: [] })
  })

  it('getKit pide /api/kit', async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify(crudo)))
    const k = await getKit(f as unknown as typeof fetch)
    expect(f).toHaveBeenCalledWith('/api/kit', expect.objectContaining({ credentials: 'same-origin' }))
    expect(k.reglas).toHaveLength(1)
  })

  it('getRegla codifica el id y devuelve el texto', async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ id: 'a b', texto: '# Hola' })))
    expect(await getRegla('a b', f as unknown as typeof fetch)).toBe('# Hola')
    expect(f.mock.calls[0][0]).toBe('/api/kit/regla/a%20b')
  })

  it('getRegla 404 es ApiError', async () => {
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify({ error: 'No encuentro esa regla' }), { status: 404 }))
    await expect(getRegla('x', f as unknown as typeof fetch)).rejects.toBeInstanceOf(ApiError)
  })

  it('arreglarKit hace POST y devuelve ok, error y estado', async () => {
    const cuerpo = { ok: false, error: 'No pude', estado: { al_dia: false, problemas: ['p'] } }
    const f = vi.fn().mockResolvedValue(new Response(JSON.stringify(cuerpo)))
    const r = await arreglarKit(f as unknown as typeof fetch)
    expect(f).toHaveBeenCalledWith('/api/kit/arreglar', expect.objectContaining({ method: 'POST' }))
    expect(r).toEqual({ ok: false, error: 'No pude', estado: { al_dia: false, problemas: ['p'] } })
  })

  it('corte de red es ApiError', async () => {
    const f = vi.fn().mockRejectedValue(new TypeError('x'))
    await expect(getKit(f as unknown as typeof fetch)).rejects.toBeInstanceOf(ApiError)
  })
})

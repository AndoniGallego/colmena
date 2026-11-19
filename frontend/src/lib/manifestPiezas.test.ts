import { describe, expect, it, vi } from 'vitest'
import { fusionarManifest, leerManifestPieza } from './manifestPiezas'

const base = { name: 'App', scope: '/', icons: [] }
const atajo = (name: string, url: string) => ({ name, short_name: name, description: 'd', url })

describe('fusionarManifest', () => {
  it('sin piezas deja el manifest como está, sin shortcuts', () => {
    expect(fusionarManifest(base, [])).toEqual(base)
    expect(fusionarManifest(base, [{}])).not.toHaveProperty('shortcuts')
  })

  it('suma los shortcuts de cada pieza en orden', () => {
    const out = fusionarManifest(base, [{ shortcuts: [atajo('A', '/?abrir=a')] }, { shortcuts: [atajo('B', '/?abrir=b')] }])
    expect(out.shortcuts?.map((s) => s.name)).toEqual(['A', 'B'])
    expect(base).not.toHaveProperty('shortcuts')
  })

  it('descarta y avisa los shortcuts fuera del scope o sin nombre', () => {
    const avisar = vi.fn()
    const out = fusionarManifest(
      base,
      [{ shortcuts: [atajo('', '/x'), atajo('Fuera', 'https://otro.example/'), atajo('Bien', '/?abrir=bien'), { name: 'Raro' } as never] }],
      avisar,
    )
    expect(out.shortcuts?.map((s) => s.name)).toEqual(['Bien'])
    expect(avisar).toHaveBeenCalledTimes(3)
  })
})

describe('leerManifestPieza', () => {
  it('devuelve el JSON de la pieza', () => {
    expect(leerManifestPieza('demo', '{"shortcuts":[]}')).toEqual({ shortcuts: [] })
  })

  it('con JSON inválido el error nombra la pieza', () => {
    expect(() => leerManifestPieza('demo', '{roto')).toThrow(/demo\/manifest\.json/)
  })
})

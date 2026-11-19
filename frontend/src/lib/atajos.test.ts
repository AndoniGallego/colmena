import { describe, expect, it } from 'vitest'
import { ATAJOS } from './atajos'

describe('ATAJOS', () => {
  it('no tiene teclas vacías ni textos vacíos', () => {
    for (const a of ATAJOS) {
      expect(a.teclas.length).toBeGreaterThan(0)
      for (const t of [...a.teclas, ...(a.tambien ?? [])]) expect(t.trim()).not.toBe('')
      expect(a.que.trim()).not.toBe('')
      expect(a.donde.trim()).not.toBe('')
    }
  })

  it('no repite el mismo atajo en el mismo lugar', () => {
    const vistos = ATAJOS.map((a) => `${a.donde}|${a.teclas.join('+')}`)
    expect(new Set(vistos).size).toBe(vistos.length)
  })

  it('incluye el buscador con Ctrl+K', () => {
    const k = ATAJOS.find((a) => a.que === 'Abrir el buscador')
    expect(k?.teclas).toEqual(['Ctrl', 'K'])
    expect(k?.mod).toBe(true)
  })

  it('incluye el atajo global para anotar desde Windows', () => {
    const a = ATAJOS.find((x) => x.que === 'Anotar desde Windows')
    expect(a?.teclas).toEqual(['Ctrl', 'Alt', 'N'])
  })
})

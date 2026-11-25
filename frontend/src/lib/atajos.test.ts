import { describe, expect, it } from 'vitest'
import { ATAJOS } from './atajos'

describe('ATAJOS', () => {
  it('no tiene teclas vacías ni textos vacíos', () => {
    for (const a of ATAJOS) {
      if (a.teclas.length === 0) expect(a.que).toContain('ícono de Colmena')
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

  it('la app de Windows tiene una sola línea que manda al ícono junto al reloj', () => {
    const w = ATAJOS.filter((x) => x.grupo === 'En la app de Windows')
    expect(w).toHaveLength(1)
    expect(w[0].que).toContain('Atajos → Cambiar atajos…')
  })

  it('los editables tienen id conocido', () => {
    const ids = ATAJOS.filter((a) => a.id).map((a) => a.id)
    expect(ids.sort()).toEqual(['buscador', 'comentar', 'crear-terminal', 'dictar', 'minimizar-preguntas'])
  })
})

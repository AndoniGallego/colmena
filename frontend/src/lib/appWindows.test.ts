import { describe, expect, it } from 'vitest'
import { enAppWindows } from './appWindows'

function memoria() {
  const store: Record<string, string> = {}
  return {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => {
      store[k] = v
    },
  }
}

describe('enAppWindows', () => {
  it('lo detecta por la URL y lo recuerda en la sesión', () => {
    const s = memoria()
    expect(enAppWindows('?app=windows&session=x', s)).toBe(true)
    expect(enAppWindows('', s)).toBe(true)
  })

  it('sin marca es la app de siempre', () => {
    expect(enAppWindows('?session=x', memoria())).toBe(false)
  })

  it('si el almacenamiento falla no rompe', () => {
    expect(
      enAppWindows('', {
        getItem: () => {
          throw new Error()
        },
        setItem: () => {},
      }),
    ).toBe(false)
  })
})

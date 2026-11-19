import { describe, expect, it } from 'vitest'

const fuentes = import.meta.glob(['../**/*.ts', '../**/*.vue', '!../**/*.test.ts', '!../bench/**', '!./index.ts'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>
const registro = import.meta.glob('./index.ts', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('plugins de GSAP registrados', () => {
  it('ScrambleText solo se registra si alguna animación usa scrambleText', () => {
    const index = Object.values(registro)[0]
    const codigo = Object.values(fuentes).join('\n')
    expect(Object.keys(fuentes).length).toBeGreaterThan(50)
    expect(/ScrambleTextPlugin/.test(index)).toBe(/scrambleText/.test(codigo))
  })
})

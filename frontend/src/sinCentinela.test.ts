import { describe, expect, it } from 'vitest'

const RUTAS = /\/api\/(centinela|planes?|cadenas|bandeja|engram\/(guardar|gate)|dios|chat)\b|permisos\/(interruptor|observacion|objecion)/
const PALABRAS = /centinela|\bdios\b|bandeja|planes|cadenas|engram\/guardar/i
const TOLERADOS = new Set(['api/types.ts', 'api/http.ts', 'lib/permisosHistorial.ts'])

function fuentes(): [string, string][] {
  const mods = import.meta.glob(['./**/*.{ts,vue}', '!./**/*.test.ts'], { query: '?raw', import: 'default', eager: true }) as Record<string, string>
  return Object.entries(mods).map(([p, src]) => [p.replace(/^\.\//, ''), src])
}

describe('el front no conoce a Centinela', () => {
  it('ningún archivo llama rutas de Centinela', () => {
    for (const [f, src] of fuentes()) expect(src, f).not.toMatch(RUTAS)
  })
  it('Centinela solo aparece en tolerancias de datos viejos', () => {
    for (const [f, src] of fuentes()) {
      if (!TOLERADOS.has(f)) expect(src.replace(/\/\/.*|\/\*[\s\S]*?\*\//g, ''), f).not.toMatch(PALABRAS)
    }
  })
})

import { describe, expect, it } from 'vitest'

const ESPECIFICADOR = /(?:from\s+|import\s*\(\s*|import\s+)['"]([^'"]+)['"]/g

function fuentes(): [string, string][] {
  const mods = import.meta.glob('../**/*.{ts,vue}', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
  return Object.entries(mods).map(([p, src]) => [p.replace(/^\.\.\//, ''), src])
}

/** Resuelve un import relativo contra la carpeta del archivo, en rutas relativas a src/. */
function resolver(desde: string, spec: string): string {
  const partes = desde.split('/').slice(0, -1)
  for (const p of spec.split('/')) {
    if (p === '..') partes.pop()
    else if (p !== '.') partes.push(p)
  }
  return partes.join('/')
}

const piezaDe = (ruta: string) => /^piezas\/([^/]+)\//.exec(ruta)?.[1] ?? null

function importsAjenos(archivos: [string, string][]): string[] {
  const out: string[] = []
  for (const [f, src] of archivos) {
    const propia = piezaDe(f)
    for (const m of src.matchAll(ESPECIFICADOR)) {
      if (!m[1].startsWith('.')) continue
      const destino = piezaDe(resolver(f, m[1]))
      if (destino && destino !== propia) out.push(`${f} -> ${m[1]}`)
    }
  }
  return out
}

describe('aislamiento de las piezas', () => {
  it('nada fuera de una pieza importa archivos de adentro de ella', () => {
    expect(importsAjenos(fuentes())).toEqual([])
  })

  it('la guarda detecta imports hacia adentro de una pieza', () => {
    expect(
      importsAjenos([
        ['App.vue', "import X from './piezas/demo/Vista.vue'"],
        ['state/algo.ts', "const m = await import('../piezas/demo/state/x')"],
        ['piezas/otra/pieza.ts', "import { y } from '../demo/lib/y'"],
        ['piezas/demo/pieza.ts', "import { z } from './lib/z'"],
        ['piezas/index.ts', "import type { Pieza } from './tipos'"],
      ]),
    ).toEqual(['App.vue -> ./piezas/demo/Vista.vue', 'state/algo.ts -> ../piezas/demo/state/x', 'piezas/otra/pieza.ts -> ../demo/lib/y'])
  })
})

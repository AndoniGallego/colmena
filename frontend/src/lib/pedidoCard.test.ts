import { describe, expect, it } from 'vitest'
import type { PedidoPermiso } from '../api/types'
import { detalleEntrada } from './pedidoCard'

const base = (herramienta: string, entrada: Record<string, unknown>): Pick<PedidoPermiso, 'herramienta' | 'entrada'> => ({
  herramienta,
  entrada,
})

describe('detalleEntrada', () => {
  it('Edit muestra ruta y antes/después', () => {
    const t = detalleEntrada(
      base('Edit', { file_path: '/a/b.ts', old_string: 'x', new_string: 'y' }),
    )
    expect(t).toContain('/a/b.ts')
    expect(t).toContain('Antes')
    expect(t).toContain('x')
    expect(t).toContain('Después')
    expect(t).toContain('y')
  })

  it('MultiEdit muestra cada edición', () => {
    const t = detalleEntrada(
      base('MultiEdit', {
        file_path: '/z.ts',
        edits: [{ old_string: '1', new_string: '2' }, { old_string: 'a', new_string: 'b' }],
      }),
    )
    expect(t).toContain('/z.ts')
    expect(t).toMatch(/Antes[\s\S]*1/)
    expect(t).toMatch(/Después[\s\S]*2/)
    expect(t).toMatch(/Antes[\s\S]*a/)
  })

  it('Write muestra ruta y content', () => {
    const t = detalleEntrada(base('Write', { file_path: '/out.txt', content: 'hola' }))
    expect(t).toContain('/out.txt')
    expect(t).toContain('hola')
  })

  it('ExitPlanMode muestra el plan completo', () => {
    const plan = 'Paso 1\nPaso 2\n'.repeat(20)
    expect(detalleEntrada(base('ExitPlanMode', { plan }))).toBe(plan)
  })

  it('Bash muestra command y description', () => {
    const t = detalleEntrada(base('Bash', { command: 'ls -la', description: 'listar' }))
    expect(t).toContain('ls -la')
    expect(t).toContain('listar')
  })

  it('otra herramienta: JSON formateado sin recortar', () => {
    const entrada = { nested: { n: 1 }, items: [1, 2, 3] }
    expect(detalleEntrada(base('Grep', entrada))).toBe(JSON.stringify(entrada, null, 2))
  })

  it('valores no string se muestran como JSON', () => {
    const t = detalleEntrada(base('Write', { file_path: '/x', content: { a: 1 } }))
    expect(t).toContain(JSON.stringify({ a: 1 }, null, 2))
  })
})

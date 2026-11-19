// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const registroPermisos = vi.hoisted(() => vi.fn())
vi.mock('../state/app', () => ({ registroPermisos }))

import PermisosHistorial from './PermisosHistorial.vue'

describe('PermisosHistorial', () => {
  beforeEach(() => registroPermisos.mockReset())

  it('lista decisiones nuevas y filas viejas', async () => {
    registroPermisos.mockResolvedValue({
      items: [
        { decision: 'rechazar', quien: 'usuario', herramienta: 'Bash', entrada: { command: 'rm x' }, hora: '2026-11-14T10:00:00Z' },
        { categoria: 'auto', quien: 'centinela', herramienta: 'Read' },
      ],
    })
    const w = mount(PermisosHistorial)
    await flushPromises()
    expect(w.text()).toContain('Rechazado')
    expect(w.text()).toContain('rm x')
    expect(w.text()).toContain('Centinela (antes)')
  })

  it('vacío', async () => {
    registroPermisos.mockResolvedValue({ items: [] })
    const w = mount(PermisosHistorial)
    await flushPromises()
    expect(w.text()).toContain('Todavía no hay permisos decididos')
  })

  it('error', async () => {
    registroPermisos.mockResolvedValue(undefined)
    const w = mount(PermisosHistorial)
    await flushPromises()
    expect(w.text()).toContain('No pude leer el historial')
  })
})

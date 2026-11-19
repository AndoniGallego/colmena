import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import { itemsDesglose } from '../lib/usoClaude'
vi.mock('../motion', () => ({ gsap: { to: () => {} }, isSoft: () => true, useGsap: () => ({ run: (fn: () => void) => fn() }) }))
import DesgloseBar from './DesgloseBar.vue'
import LimiteRing from './LimiteRing.vue'

const tk = (total: number, mensajes = 2) => ({ input: total / 10, cache_write: 0, cache_read: (total * 8) / 10, output: total / 10, mensajes, total })
const render = (comp: any, props: Record<string, unknown>) => renderToString(createSSRApp({ render: () => h(comp, props) }))

describe('DesgloseBar', () => {
  it('por tipo de token sigue igual que antes', async () => {
    const html = await render(DesgloseBar, { tokens: tk(1000) })
    expect(html).toContain('Leído de caché')
    expect(html).not.toContain('<button')
    expect(html).not.toContain('role="tooltip"')
  })

  it('con filas muestra nombre, detalle y el desglose para hover', async () => {
    const items = itemsDesglose([
      { id: 's1', nombre: 'Arreglar login', detalle: 'tienda', tipo: '', ...tk(9000, 4) },
      { id: 's2', nombre: 'Otra sesión', detalle: 'kit', tipo: '', ...tk(1000, 1) },
    ])
    const html = await render(DesgloseBar, { items, label: 'Uso por sesiones hoy' })
    expect(html).toContain('aria-label="Uso por sesiones hoy"')
    expect(html).toContain('Arreglar login')
    expect(html).toContain('tienda')
    expect(html).not.toContain('data-tipo="centinela"')
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain('900 entrada · 7.2 k caché · 900 salida · 4 mensajes')
    expect(html).toMatch(/>90<!--[^>]*-->%|>90%/)
  })
})

describe('LimiteRing', () => {
  it('dice el porcentaje y cuándo se reinicia', async () => {
    const html = await render(LimiteRing, { pct: 63, titulo: 'Últimas 5 horas', reinicio: 'se reinicia en 2 h' })
    expect(html).toContain('Últimas 5 horas: 63% usado, se reinicia en 2 h')
    expect(html).toContain('data-estado="ok"')
  })
  it('vencido no muestra un número viejo', async () => {
    const html = await render(LimiteRing, { pct: 97, titulo: 'Semana', reinicio: 'ya se reinició', vencido: true })
    expect(html).toContain('Semana: reiniciado')
    expect(html).toContain('sin dato nuevo')
  })
})

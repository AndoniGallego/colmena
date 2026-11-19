import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it } from 'vitest'
import type { Subagente } from '../api/types'
import SubagentesStrip from './SubagentesStrip.vue'

const mk = (id: string, estado: Subagente['estado'], segundos: number, paso: string): Subagente => ({ id, descripcion: `Tarea ${id}`, tipo: '', modelo: 'sonnet', estado, inicio: '', segundos, paso, tokens: null })

const render = (items: Subagente[]) => renderToString(createSSRApp({ render: () => h(SubagentesStrip, { items }) }))

describe('SubagentesStrip', () => {
  it('no muestra nada sin agentes', async () => {
    expect(await render([])).not.toContain('class="subs')
  })
  it('entra colapsada con el conteo y el paso del más reciente', async () => {
    const html = await render([mk('a', 'trabajando', 90, 'Leyendo transcript.py'), mk('b', 'trabajando', 10, 'Corriendo pruebas'), mk('c', 'termino', 5, 'Terminó')])
    expect(html).toContain('aria-expanded="false"')
    expect(html).toMatch(/class="drawer"[^>]*inert/)
    expect(html).toContain('2 agentes trabajando')
    expect(html).toMatch(/class="now"[^>]*>Corriendo pruebas</)
    expect(html).toContain('class="orb"')
  })
  it('sin agentes trabajando muestra el tilde y no la animación', async () => {
    const html = await render([mk('c', 'termino', 5, 'Terminó')])
    expect(html).toContain('1 agente terminó')
    expect(html).not.toContain('class="orb"')
  })
})

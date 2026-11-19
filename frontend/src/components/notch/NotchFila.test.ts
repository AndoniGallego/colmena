// @vitest-environment jsdom
import { mount } from '@vue/test-utils'
import { createSSRApp, h, nextTick } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

const { NOW_MOCK } = vi.hoisted(() => ({
  NOW_MOCK: Date.parse('2026-11-04T18:00:00Z'),
}))

vi.hoisted(() => {
  vi.stubGlobal('window', { matchMedia: () => ({ matches: false, addEventListener() {} }), addEventListener() {} })
})

vi.mock('../../lib/time', async (importOriginal) => {
  const { ref } = await import('vue')
  return { ...(await importOriginal<typeof import('../../lib/time')>()), useNow: () => ref(NOW_MOCK) }
})
import type { FormaRespuesta } from '../../lib/notchRespuesta'
import type { SesionNotch } from '../../lib/notchCeldas'
import type { EstadoFila } from '../../state/notchRespuesta'

vi.mock('../../motion', async () => {
  const { ref } = await import('vue')
  return {
    gsap: {
      set() {},
      to() {},
      fromTo() {},
      from() {},
      timeline: () => ({ to() { return this }, fromTo() { return this }, kill() {} }),
      delayedCall() {},
      utils: { random: () => 1 },
    },
    isSoft: () => true,
    soft: ref(true),
    brandHop: ref(0),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})

const NOW = Date.parse('2026-11-04T18:00:00Z')

const teToca: SesionNotch = {
  pane_id: 'pa',
  session_id: 'a',
  titulo: 'Sesión a',
  donde: 'Acme · 1',
  estado: 'te-toca',
  motivo: 'pregunta',
  preguntas: 0,
  desdeMs: null,
  linea: 'Te toca',
  last_activity: null,
  hue: 120,
}

const formaOpc: FormaRespuesta = {
  tipo: 'opciones',
  pregunta: '¿Avanzo?',
  opciones: ['Sí', 'No'],
  otro: true,
  via: 'dialogo',
}

const render = async (props: {
  sesion: SesionNotch
  now: number
  forma?: FormaRespuesta
  estado?: EstadoFila
  activa?: boolean
}) => {
  const { default: NotchFila } = await import('./NotchFila.vue')
  return renderToString(createSSRApp({ render: () => h(NotchFila, props) }))
}

describe('NotchFila respuestas', () => {
  it('te toca: el título es un botón para abrir en Colmena', async () => {
    const html = await render({ sesion: teToca, forma: formaOpc, now: NOW, activa: true })
    expect(html).toContain('class="titulo"')
    expect(html).toContain('type="button"')
    expect(html).toContain('title="Abrir en Colmena"')
    expect(html).toContain('aria-label="Abrir Sesión a en Colmena"')
    expect(html).toContain('Sesión a')
  })

  it('trabajando: el título sigue siendo texto, no botón titulo', async () => {
    const html = await render({
      sesion: { ...teToca, estado: 'trabajando', linea: 'Trabajando…' },
      now: NOW,
    })
    expect(html).not.toContain('class="titulo"')
  })

  it('te toca con 2 opciones cortas: botones en fila, Otra cosa… y nunca Permitir siempre', async () => {
    const html = await render({ sesion: teToca, forma: formaOpc, now: NOW, activa: true })
    expect(html).toContain('¿Avanzo?')
    expect(html).toContain('Otra cosa…')
    expect(html).not.toContain('Escribir otra respuesta')
    expect(html).not.toContain('Permitir siempre')
  })

  it('te toca con opciones apiladas: números, labels, rec y fila para otra respuesta', async () => {
    const html = await render({
      sesion: teToca,
      now: NOW,
      activa: true,
      forma: {
        tipo: 'opciones',
        pregunta: '¿Qué hacemos?',
        opciones: [
          'Reescribir el historial de la rama',
          'Aplastar todo en un commit',
          'Permitir el .gitleaksignore en el check',
          'Lo hablo con el equipo primero',
        ],
        otro: true,
        via: 'dialogo',
      },
    })
    expect(html).toMatch(/class="(?:acts apiladas|apiladas acts)"/)
    expect(html).toContain('class="n"')
    expect(html).toContain('class="lb"')
    expect(html).toContain('>1<')
    expect(html).toContain('>4<')
    expect(html).toContain('Reescribir el historial de la rama')
    expect(html).toMatch(/class="[^"]*\brec\b[^"]*"/)
    expect(html).toContain('Escribir otra respuesta…')
    expect(html).not.toContain('Otra cosa…')
  })

  it('te toca con 2 opciones cortas: acts sin apiladas', async () => {
    const html = await render({ sesion: teToca, forma: formaOpc, now: NOW, activa: true })
    expect(html).toMatch(/class="acts"/)
    expect(html).not.toMatch(/\bapiladas\b/)
  })

  it('permiso: Permitir y Rechazar', async () => {
    const html = await render({
      sesion: teToca,
      now: NOW,
      activa: true,
      forma: {
        tipo: 'permiso',
        titulo: 'Quiere correr un comando',
        detalle: 'npm test',
        puedePermitir: true,
        via: 'dialogo',
      },
    })
    expect(html).toContain('Permitir')
    expect(html).toContain('Rechazar')
    expect(html).not.toContain('siempre')
  })

  it('permiso incompleto: solo Rechazar', async () => {
    const html = await render({
      sesion: teToca,
      now: NOW,
      activa: true,
      forma: {
        tipo: 'permiso',
        titulo: 'Quiere correr un comando',
        detalle: 'npm test',
        puedePermitir: false,
        via: 'dialogo',
      },
    })
    expect(html).toContain('Rechazar')
    expect(html).not.toMatch(/>Permitir</)
  })

  it('cambio: muestra el aviso y el botón para abrir', async () => {
    const html = await render({
      sesion: teToca,
      forma: formaOpc,
      estado: { fase: 'cambio', mensaje: 'La sesión cambió, abrila en Colmena' },
      now: NOW,
      activa: true,
    })
    expect(html).toContain('La sesión cambió, abrila en Colmena')
    expect(html).toContain('Abrir en Colmena')
  })

  it('enviado: muestra la confirmación', async () => {
    const html = await render({
      sesion: teToca,
      forma: formaOpc,
      estado: { fase: 'enviado' },
      now: NOW,
      activa: true,
    })
    expect(html).toContain('✓ Enviado a la sesión')
  })

  it('enviado en trabajando: sigue mostrando la confirmación', async () => {
    const html = await render({
      sesion: { ...teToca, estado: 'trabajando', linea: 'Trabajando…' },
      estado: { fase: 'enviado' },
      now: NOW,
    })
    expect(html).toContain('✓ Enviado a la sesión')
  })

  it('espacio en input libre no hace preventDefault', async () => {
    const { default: NotchFila } = await import('./NotchFila.vue')
    const w = mount(NotchFila, {
      props: { sesion: teToca, forma: formaOpc, now: NOW, activa: true },
    })
    ;(w.get('button.chip.ghost').element as HTMLButtonElement).click()
    await nextTick()
    const input = w.get('input')
    const ev = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    const spy = vi.spyOn(ev, 'preventDefault')
    input.element.dispatchEvent(ev)
    expect(spy).not.toHaveBeenCalled()
  })

  it('espacio en la fila (no input) sigue activando la fila', async () => {
    const { default: NotchFila } = await import('./NotchFila.vue')
    const trabajando = { ...teToca, estado: 'trabajando' as const, linea: 'En curso' }
    const w = mount(NotchFila, {
      props: { sesion: trabajando, now: NOW },
    })
    const ev = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true })
    const spy = vi.spyOn(ev, 'preventDefault')
    w.get('.row').element.dispatchEvent(ev)
    expect(spy).toHaveBeenCalled()
  })

  it('enviando: botones deshabilitados', async () => {
    const html = await render({
      sesion: teToca,
      forma: formaOpc,
      estado: { fase: 'enviando' },
      now: NOW,
      activa: true,
    })
    expect(html).toContain('aria-busy="true"')
    expect(html).toContain('disabled')
  })
})

describe('NotchFila con pedido', () => {
  const pedido = (over: Partial<Extract<FormaRespuesta, { tipo: 'pedido' }>> = {}): FormaRespuesta => ({
    tipo: 'pedido',
    pedidoId: 'p1',
    titulo: 'Abrir pestaña',
    detalle: '/tmp/demo',
    boton: 'Abrir',
    aviso: '',
    enviando: false,
    error: '',
    donde: '',
    ariaAceptar: 'Abrir pestaña',
    ariaRechazar: 'No abrir',
    ...over,
  })
  const montar = async (forma: FormaRespuesta) => {
    const { default: NotchFila } = await import('./NotchFila.vue')
    return mount(NotchFila, { props: { sesion: { ...teToca, motivo: 'pedido' }, now: NOW, activa: false, forma } })
  }

  it('muestra título, detalle y Abrir/No sin pasar por Ver opciones', async () => {
    const w = await montar(pedido())
    expect(w.text()).toContain('Abrir pestaña')
    expect(w.text()).toContain('/tmp/demo')
    expect(w.text()).not.toContain('Ver opciones')
    w.findAll('button').find((b) => b.text() === 'Abrir')!.element.click()
    w.findAll('button').find((b) => b.text() === 'No')!.element.click()
    expect(w.emitted('pedido')).toEqual([['aceptar', 'p1'], ['rechazar', 'p1']])
  })

  it('los botones dicen a qué responden', async () => {
    const w = await montar(pedido({ titulo: 'Cerrar pestaña', boton: 'Cerrar', ariaAceptar: 'Cerrar la pestaña', ariaRechazar: 'No cerrar' }))
    expect(w.findAll('button').find((b) => b.text() === 'Cerrar')!.attributes('aria-label')).toBe('Cerrar la pestaña')
    expect(w.findAll('button').find((b) => b.text() === 'No')!.attributes('aria-label')).toBe('No cerrar')
  })

  it('un cierre muestra el espacio y el id del objetivo', async () => {
    const w = await montar(pedido({ titulo: 'Cerrar pestaña', donde: 'Tienda · w2:t1' }))
    expect(w.text()).toContain('Tienda · w2:t1')
  })

  it('la región del aviso está montada aunque no haya aviso', async () => {
    const w = await montar(pedido())
    expect(w.find('[role="status"]').exists()).toBe(true)
    expect(w.find('[role="status"]').text()).toBe('')
  })

  it('un cierre trabajando muestra el aviso y Cerrar igual en rojo', async () => {
    const w = await montar(pedido({ titulo: 'Cerrar pestaña', boton: 'Cerrar igual', aviso: 'Está trabajando' }))
    expect(w.text()).toContain('Está trabajando')
    const b = w.findAll('button').find((x) => x.text() === 'Cerrar igual')!
    expect(b.classes()).toContain('peligro')
    expect(w.findAll('button').find((x) => x.text() === 'No')!.classes()).not.toContain('peligro')
  })

  it('un abrir no marca el botón como peligro', async () => {
    const w = await montar(pedido())
    expect(w.findAll('button').find((x) => x.text() === 'Abrir')!.classes()).not.toContain('peligro')
  })

  it('el error se anuncia con role alert', async () => {
    const w = await montar(pedido({ error: 'No pude cerrarlo' }))
    expect(w.find('[role="alert"]').text()).toBe('No pude cerrarlo')
  })

  it('mientras se envía, los botones quedan deshabilitados', async () => {
    const w = await montar(pedido({ enviando: true }))
    const bs = w.findAll('button').filter((b) => ['Abrir', 'No'].includes(b.text()))
    expect(bs).toHaveLength(2)
    expect(bs.every((b) => b.attributes('disabled') !== undefined)).toBe(true)
  })
})

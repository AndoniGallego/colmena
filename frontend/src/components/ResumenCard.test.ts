// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const marcarPropuesta = vi.fn()
const postNueva = vi.hoisted(() => vi.fn())
vi.mock('../state/app', () => ({
  marcarPropuesta: (...a: unknown[]) => marcarPropuesta(...a),
  postTerminalesNuevaTarea: (...a: unknown[]) => postNueva(...a),
}))

vi.mock('./NuevaTerminalSheet.vue', () => ({
  default: {
    name: 'NuevaTerminalSheet',
    props: { open: Boolean, tareaInicial: { type: String, default: undefined } },
    emits: ['close'],
    template: '<div class="hoja-stub" :data-open="String(open)">{{ tareaInicial }}</div>',
  },
}))

const { default: ResumenCard } = await import('./ResumenCard.vue')

const cand = (id: string, texto: string) => ({
  id, regla: 'error_repetido', clave: 'k', texto, metrica: { nombre: 'veces', valor: 24 }, peso: 1.2,
})

const data = (over: Record<string, unknown> = {}) => ({
  semana: '2026-W47',
  desde: '2026-11-16',
  hasta: '2026-11-22',
  resumen: {
    errores: { top: [{ plantilla: 'boom', logger: 'x', tipo_exc: 'ValueError', n: 24, delta: 4, hace: 'hace 2 h' }], ya_no: [] },
    pedidos: { por_tipo: { abrir: 3, cerrar: 1 }, por_origen: {}, por_motivo: { rechazado: { sin_permiso: 2 }, vencido: { sin_motivo: 1 } }, mediana_s: 4 },
    respuesta: { asks: { en_app: { mediana_s: 12, p90_s: 40, n: 5 }, celu: { mediana_s: 90, p90_s: 200, n: 3 } }, blocked: { en_app: { mediana_s: null, p90_s: null, n: 0 }, celu: { mediana_s: null, p90_s: null, n: 0 } }, sin_respuesta: 2 },
    trabas: { por_tipo: { permiso: 2 }, mediana_s: 30, por_fin: { resuelta: 2 } },
    comandos: { corridos: 7, fallos: { '1': 2 }, no: 1 },
    cierres: { frenados: 5, resueltos_pct: 80 },
    app: { errores: { 'web/500': 3 }, tuneles_fallidos: 1, desconexiones: 0 },
  },
  propuestas: {
    nuevas: [cand('aaaaaaaaaaaa', 'El error boom se repitió 24 veces'), cand('bbbbbbbbbbbb', 'Los pedidos vencen seguido')],
    mas_adelante: [cand('cccccccccccc', 'Ajustar el aviso de respuesta lenta')],
    seguimiento: [{ id: 'dddddddddddd', texto: 'Errores de cierre', base: 10, valor: 4, tendencia: 'baja' }],
    volvio: [],
  },
  ...over,
})

const montar = (d = data()) => mount(ResumenCard, { props: { data: d as never, itemId: 'i'.repeat(32) } })

beforeEach(() => {
  marcarPropuesta.mockReset()
})

describe('ResumenCard', () => {
  it('muestra las propuestas con su dato', () => {
    const w = montar()
    const props = w.findAll('section[aria-label="Propuestas"] .propuesta')
    expect(props).toHaveLength(2)
    expect(props[0].text()).toContain('El error boom se repitió 24 veces')
    expect(props[1].text()).toContain('Los pedidos vencen seguido')
    for (const p of props) expect(p.findAll('button.decision')).toHaveLength(3)
    expect(props[0].findAll('button.decision').map((b) => b.text())).toEqual(['Hacer', 'Ignorar 30 días', 'Más adelante'])
  })

  it('Ignorar llama al endpoint y muestra la marca', async () => {
    marcarPropuesta.mockResolvedValue({ id: 'aaaaaaaaaaaa', estado: 'ignorada' })
    const w = montar()
    await w.findAll('.propuesta')[0].findAll('button.decision')[1].trigger('click')
    await flushPromises()
    expect(marcarPropuesta).toHaveBeenCalledWith('aaaaaaaaaaaa', 'ignorar')
    const p = w.findAll('.propuesta')[0]
    expect(p.text()).toContain('Marcada: ignorar')
    expect(p.findAll('button.decision').map((b) => b.attributes('aria-pressed'))).toEqual(['false', 'true', 'false'])
    expect(w.emitted('hacer')).toBeUndefined()
  })

  it('si marcar falla, el botón no queda marcado y avisa', async () => {
    marcarPropuesta.mockRejectedValue(new Error('caído'))
    const w = montar()
    await w.findAll('.propuesta')[0].findAll('button.decision')[2].trigger('click')
    await flushPromises()
    const p = w.findAll('.propuesta')[0]
    expect(p.findAll('button.decision').every((b) => b.attributes('aria-pressed') !== 'true')).toBe(true)
    expect(p.find('[role="alert"]').text()).toContain('No pude guardar')
    expect(p.text()).not.toContain('Marcada')
  })

  it('si Hacer falla, no queda marcado, avisa y no emite hacer', async () => {
    marcarPropuesta.mockRejectedValue(new Error('caído'))
    const w = montar()
    await w.findAll('.propuesta')[0].findAll('button.decision')[0].trigger('click')
    await flushPromises()
    const p = w.findAll('.propuesta')[0]
    expect(p.findAll('button.decision').every((b) => b.attributes('aria-pressed') === 'false')).toBe(true)
    expect(p.find('[role="alert"]').text()).toContain('No pude guardar')
    expect(w.emitted('hacer')).toBeUndefined()
  })

  it('Hacer marca y emite hacer', async () => {
    marcarPropuesta.mockResolvedValue({ id: 'bbbbbbbbbbbb', estado: 'hacer' })
    const w = montar()
    await w.findAll('.propuesta')[1].findAll('button.decision')[0].trigger('click')
    await flushPromises()
    expect(marcarPropuesta).toHaveBeenCalledWith('bbbbbbbbbbbb', 'hacer')
    expect((w.emitted('hacer') as { id: string }[][])[0][0].id).toBe('bbbbbbbbbbbb')
    expect(w.findAll('.propuesta')[1].text()).toContain('Marcada: hacer')
  })

  it('Hacer abre la hoja con el brief y no lanza nada', async () => {
    marcarPropuesta.mockResolvedValue({ id: 'bbbbbbbbbbbb', estado: 'hacer' })
    const w = montar()
    expect(w.find('.hoja-stub').attributes('data-open')).toBe('false')
    await w.findAll('.propuesta')[1].findAll('button.decision')[0].trigger('click')
    await flushPromises()
    const hoja = w.find('.hoja-stub')
    expect(hoja.attributes('data-open')).toBe('true')
    expect(hoja.text()).toContain('Propuesta del resumen de la semana 2026-W47: Los pedidos vencen seguido')
    expect(hoja.text()).toContain('Métrica: veces = 24')
    expect(postNueva).not.toHaveBeenCalled()
  })

  it('Ignorar y un Hacer que falla no abren la hoja; cerrarla deja la tarjeta usable', async () => {
    marcarPropuesta.mockRejectedValueOnce(new Error('caído'))
    const w = montar()
    await w.findAll('.propuesta')[0].findAll('button.decision')[0].trigger('click')
    await flushPromises()
    expect(w.find('.hoja-stub').attributes('data-open')).toBe('false')
    marcarPropuesta.mockResolvedValue({ id: 'bbbbbbbbbbbb', estado: 'hacer' })
    await w.findAll('.propuesta')[1].findAll('button.decision')[0].trigger('click')
    await flushPromises()
    expect(w.find('.hoja-stub').attributes('data-open')).toBe('true')
    await w.findComponent({ name: 'NuevaTerminalSheet' }).vm.$emit('close')
    await flushPromises()
    expect(w.find('.hoja-stub').attributes('data-open')).toBe('false')
    expect(w.findAll('.propuesta')[1].findAll('button.decision').every((b) => !b.attributes('disabled'))).toBe(true)
  })

  it('Más adelante marca con su texto', async () => {
    marcarPropuesta.mockResolvedValue({ id: 'aaaaaaaaaaaa', estado: 'mas_adelante' })
    const w = montar()
    await w.findAll('.propuesta')[0].findAll('button.decision')[2].trigger('click')
    await flushPromises()
    expect(marcarPropuesta).toHaveBeenCalledWith('aaaaaaaaaaaa', 'mas_adelante')
    expect(w.findAll('.propuesta')[0].text()).toContain('Marcada: más adelante')
    expect(w.emitted('hacer')).toBeUndefined()
  })

  it('sin propuestas muestra el vacío', () => {
    const w = montar(data({ propuestas: { nuevas: [], mas_adelante: [], seguimiento: [], volvio: [] } }))
    expect(w.text()).toContain('Esta semana no hay nada para proponer')
    expect(w.find('.propuesta').exists()).toBe(false)
  })

  it('las secciones se pliegan', async () => {
    const w = montar()
    const cab = w.findAll('button.sec-cab').find((b) => b.text().includes('Errores'))!
    const antes = cab.attributes('aria-expanded')
    await cab.trigger('click')
    expect(cab.attributes('aria-expanded')).not.toBe(antes)
    await cab.trigger('click')
    expect(cab.attributes('aria-expanded')).toBe(antes)
  })

  it('cada sección trae su número grande', () => {
    const w = montar()
    const num = (t: string): string => w.findAll('button.sec-cab').find((b) => b.text().includes(t))!.find('.num').text()
    expect(num('Errores')).toBe('24')
    expect(num('Pedidos')).toBe('4')
    expect(num('Comandos')).toBe('7')
    expect(num('Seguimiento')).toBe('1')
  })

  it('lista lo que queda para más adelante al pie', () => {
    const w = montar()
    expect(w.find('.pie').text()).toContain('Para más adelante')
    expect(w.find('.pie').text()).toContain('Ajustar el aviso de respuesta lenta')
  })

  it('no rompe si faltan secciones', () => {
    const w = montar({ semana: '2026-W47', desde: '', hasta: '' } as never)
    expect(w.text()).toContain('Esta semana no hay nada para proponer')
  })

  it.each([['bajo', 'Bajó'], ['subio', 'Subió'], ['igual', 'Igual']])('el seguimiento con tendencia %s muestra %s', async (tendencia, texto) => {
    const d = data()
    d.propuestas.seguimiento = [{ id: 'dddddddddddd', texto: 'Errores de cierre', base: 10, valor: 4, tendencia }]
    const w = montar(d)
    await w.findAll('button.sec-cab').find((b) => b.text().includes('Seguimiento'))!.trigger('click')
    expect(w.find('.detalle').text()).toContain(texto)
  })

  const abrir = async (w: ReturnType<typeof montar>, titulo: string) => {
    await w.findAll('button.sec-cab').find((b) => b.text().includes(titulo))!.trigger('click')
    return w.find('.sec-cuerpo').text()
  }

  it('Pedidos despliega por tipo y por estado con su motivo', async () => {
    const t = await abrir(montar(), 'Pedidos')
    expect(t).toContain('abrir')
    expect(t).toContain('3')
    expect(t).toContain('Rechazados')
    expect(t).toContain('sin_permiso')
  })

  it('Respuesta despliega las medianas y los que quedaron sin respuesta', async () => {
    const t = await abrir(montar(), 'Respuesta')
    expect(t).toContain('12 s')
    expect(t).toContain('Sin respuesta')
    expect(t).toContain('2')
  })

  it('Trabas despliega por tipo y cómo terminaron', async () => {
    const t = await abrir(montar(), 'Trabas')
    expect(t).toContain('permiso')
    expect(t).toContain('resuelta')
  })

  it('Comandos despliega corridos, fallos y rechazados', async () => {
    const t = await abrir(montar(), 'Comandos')
    expect(t).toContain('Corridos')
    expect(t).toContain('código 1')
    expect(t).toContain('Rechazados')
  })

  it('Cierres despliega frenados y el porcentaje resuelto', async () => {
    const t = await abrir(montar(), 'Cierres')
    expect(t).toContain('Frenados')
    expect(t).toContain('80%')
  })

  it('App despliega errores, túneles fallidos y desconexiones', async () => {
    const t = await abrir(montar(), 'App')
    expect(t).toContain('web/500')
    expect(t).toContain('Túneles fallidos')
    expect(t).toContain('Desconexiones')
  })

  it('el pie "Para más adelante" tiene los mismos botones y decide', async () => {
    marcarPropuesta.mockResolvedValue({ id: 'cccccccccccc', estado: 'ignorada' })
    const w = montar()
    const pie = w.find('section.pie')
    const items = pie.findAll('.propuesta')
    expect(items).toHaveLength(1)
    expect(items[0].text()).toContain('Ajustar el aviso de respuesta lenta')
    expect(items[0].findAll('button.decision').map((b) => b.text())).toEqual(['Hacer', 'Ignorar 30 días', 'Más adelante'])
    await items[0].findAll('button.decision')[1].trigger('click')
    await flushPromises()
    expect(marcarPropuesta).toHaveBeenCalledWith('cccccccccccc', 'ignorar')
    expect(items[0].text()).toContain('Marcada: ignorar')
  })
})

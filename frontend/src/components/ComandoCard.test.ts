// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const correrComando = vi.fn()
vi.mock('../state/app', () => ({ correrComando: (...a: unknown[]) => correrComando(...a) }))

const { default: ComandoCard } = await import('./ComandoCard.vue')
const { olvidarComandos } = await import('../lib/comando')

const LARGO = 'docker compose -f /home/usuario/proyecto/docker-compose.yml exec -T php bin/console cache:clear --env=prod --no-warmup'
const props = (over: Record<string, unknown> = {}) => ({
  data: { comando: LARGO, motivo: 'Limpia la caché', carpeta: '/home/usuario/proyecto' },
  sessionId: 's1',
  mid: 'mid-aaaaaaaa',
  indice: 2,
  ...over,
})

beforeEach(() => {
  correrComando.mockReset()
  olvidarComandos()
})

describe('ComandoCard', () => {
  it('muestra el comando exacto, el motivo y dónde corre de verdad', () => {
    const w = mount(ComandoCard, { props: props({ cwd: '/home/usuario/proyecto/' }) })
    expect(w.find('.cmd').text()).toBe(LARGO)
    expect(w.text()).toContain('Limpia la caché')
    expect(w.find('.carpeta').text()).toBe('Corre en: /home/usuario/proyecto/')
    expect(w.find('button.correr').exists()).toBe(true)
    expect(w.find('button.no').exists()).toBe(true)
  })

  it('Correr manda sesión, mensaje, índice y el texto mostrado, y queda Corrido', async () => {
    correrComando.mockResolvedValue({ ok: true, comando: LARGO })
    const w = mount(ComandoCard, { props: props() })
    await w.find('button.correr').trigger('click')
    await flushPromises()
    expect(correrComando).toHaveBeenCalledWith('s1', { mid: 'mid-aaaaaaaa', indice: 2, comando: LARGO })
    expect(w.text()).toContain('Corrido')
    expect(w.find('button.correr').exists()).toBe(false)
  })

  it('No lo deja Descartado sin llamar al servidor', async () => {
    const w = mount(ComandoCard, { props: props() })
    await w.find('button.no').trigger('click')
    expect(correrComando).not.toHaveBeenCalled()
    expect(w.text()).toContain('Descartado')
  })

  it('un error del servidor se muestra y deja reintentar', async () => {
    correrComando.mockRejectedValue(new ApiError(409, 'La sesión está trabajando; probá cuando termine'))
    const w = mount(ComandoCard, { props: props() })
    await w.find('button.correr').trigger('click')
    await flushPromises()
    expect(w.find('[role="alert"]').text()).toContain('La sesión está trabajando')
    expect(w.find('button.correr').exists()).toBe(true)
  })

  it('si ya se corrió (409) queda como Corrido', async () => {
    correrComando.mockRejectedValue(new ApiError(409, 'Ese comando ya se corrió'))
    const w = mount(ComandoCard, { props: props() })
    await w.find('button.correr').trigger('click')
    await flushPromises()
    expect(w.text()).toContain('Ya se corrió')
    expect(w.find('button.correr').exists()).toBe(false)
  })

  it('Enter con la tarjeta enfocada corre y Esc descarta', async () => {
    correrComando.mockResolvedValue({ ok: true, comando: LARGO })
    const w = mount(ComandoCard, { props: props() })
    await w.find('article').trigger('keydown', { key: 'Enter' })
    await flushPromises()
    expect(correrComando).toHaveBeenCalledTimes(1)
    const w2 = mount(ComandoCard, { props: props({ indice: 3 }) })
    const ev = new KeyboardEvent('keydown', { key: 'Escape', cancelable: true, bubbles: true })
    w2.find('article').element.dispatchEvent(ev)
    await flushPromises()
    expect(ev.defaultPrevented).toBe(true)
    expect(w2.text()).toContain('Descartado')
  })

  it('el estado sobrevive a montar de nuevo la misma tarjeta', async () => {
    const w = mount(ComandoCard, { props: props() })
    await w.find('button.no').trigger('click')
    const otra = mount(ComandoCard, { props: props() })
    expect(otra.text()).toContain('Descartado')
  })

  it('sin sesión o id de mensaje no ofrece Correr', () => {
    const w = mount(ComandoCard, { props: props({ mid: undefined }) })
    expect(w.find('button.correr').exists()).toBe(false)
  })

  it('un comando inválido no ofrece Correr y explica por qué', () => {
    const w = mount(ComandoCard, { props: props({ data: { comando: 'a\nb', motivo: '', error: 'tiene más de una línea' } }) })
    expect(w.find('button.correr').exists()).toBe(false)
    expect(w.text()).toContain('tiene más de una línea')
  })

  it('el comando se muestra de izquierda a derecha y aislado', () => {
    const w = mount(ComandoCard, { props: props() })
    expect(w.find('.cmd').attributes('dir')).toBe('ltr')
  })

  it('resalta los caracteres no comunes y avisa', () => {
    const w = mount(ComandoCard, { props: props({ data: { comando: 'cat /etc/раsswd', motivo: '' } }) })
    expect(w.find('.cmd').text()).toBe('cat /etc/раsswd')
    expect(w.findAll('.cmd .rara').map((e) => e.text())).toEqual(['ра'])
    expect(w.text()).toContain('Tiene caracteres no comunes')
  })

  it('un comando solo ASCII no avisa', () => {
    const w = mount(ComandoCard, { props: props() })
    expect(w.find('.cmd .rara').exists()).toBe(false)
    expect(w.text()).not.toContain('Tiene caracteres no comunes')
  })

  it('si la carpeta pedida no es el cwd real la tarjeta es inválida', () => {
    const w = mount(ComandoCard, { props: props({ cwd: '/home/otro' }) })
    expect(w.find('button.correr').exists()).toBe(false)
    expect(w.text()).toContain('La carpeta pedida no es donde corre la sesión')
    expect(w.find('.carpeta').text()).toBe('Corre en: /home/otro')
  })

  it('sin cwd conocido no muestra la carpeta del bloque como si fuera donde corre', () => {
    const w = mount(ComandoCard, { props: props({ data: { comando: 'ls', motivo: '', carpeta: '/home/x' } }) })
    expect(w.text()).not.toContain('/home/x')
    expect(w.find('.carpeta').text()).toBe('Corre en la carpeta de la sesión')
  })
})

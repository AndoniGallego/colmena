// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { Entorno, ResultadoPrueba } from '../api/entornosApi'
import { ApiError } from '../api/types'

const resultadoOk = (): ResultadoPrueba => ({
  codigo: 200,
  ms: 12,
  tipo: 'text/html',
  encabezados: [],
  cuerpo: 'ok',
  bytes: 2,
  truncado: false,
})

const entorno = (): Entorno => ({
  nombre: 'hs',
  carpeta: '~/x',
  principal: 9000,
  salud: null,
  apagado: false,
  servicios: [],
  puertos: [{ puerto: 9000, servicio: 'hs-api', puerto_contenedor: null, abrible: true }],
})

const { default: EntornosProbador } = await import('./EntornosProbador.vue')

function botonEnviar(w: ReturnType<typeof mount>) {
  return w.findAll('button').find((b) => {
    const t = b.text()
    return t === 'Enviar' || t.startsWith('Confirmar')
  })!
}

describe('EntornosProbador', () => {
  it('aria-live polite existe antes de enviar', async () => {
    const w = mount(EntornosProbador, { props: { entorno: entorno(), probar: vi.fn() }, attachTo: document.body })
    await flushPromises()
    expect(w.find('[aria-live="polite"]').exists()).toBe(true)
    w.unmount()
  })

  it('GET no muestra textarea; POST sí', async () => {
    const probar = vi.fn().mockResolvedValue(resultadoOk())
    const w = mount(EntornosProbador, { props: { entorno: entorno(), probar }, attachTo: document.body })
    await flushPromises()
    expect(w.find('textarea').exists()).toBe(false)
    await w.find('#pr-metodo').setValue('POST')
    await flushPromises()
    expect(w.find('textarea').exists()).toBe(true)
    w.unmount()
  })

  it('POST primer clic confirma sin llamar; segundo confirma true; cambiar ruta resetea', async () => {
    const probar = vi.fn().mockResolvedValue(resultadoOk())
    const w = mount(EntornosProbador, { props: { entorno: entorno(), probar }, attachTo: document.body })
    await flushPromises()
    await w.find('#pr-metodo').setValue('POST')
    await flushPromises()
    await botonEnviar(w).trigger('click')
    await flushPromises()
    expect(probar).not.toHaveBeenCalled()
    expect(w.text()).toContain('Confirmar POST a hs-api')
    await botonEnviar(w).trigger('click')
    await flushPromises()
    expect(probar).toHaveBeenCalledWith(expect.objectContaining({ confirmado: true, metodo: 'POST' }))
    await w.find('#pr-ruta').setValue('/api/x')
    await flushPromises()
    expect(w.text()).toContain('Enviar')
    expect(w.text()).not.toContain('Confirmar POST a hs-api')
    w.unmount()
  })

  it('cuerpo XSS queda literal en pre sin img', async () => {
    const xss = '<img src=x onerror=alert(1)>'
    const probar = vi.fn().mockResolvedValue({ ...resultadoOk(), cuerpo: xss, tipo: 'text/html' })
    const w = mount(EntornosProbador, { props: { entorno: entorno(), probar }, attachTo: document.body })
    await flushPromises()
    await botonEnviar(w).trigger('click')
    await flushPromises()
    const pre = w.find('pre.pr-cuerpo')
    expect(pre.text()).toBe(xss)
    expect(pre.element.querySelector('img')).toBeNull()
    w.unmount()
  })

  it('JSON indentado, truncado y ApiError en pr-error', async () => {
    let probar = vi.fn().mockResolvedValue({
      ...resultadoOk(),
      cuerpo: '{"a":1}',
      tipo: 'application/json',
      truncado: true,
    })
    const w = mount(EntornosProbador, { props: { entorno: entorno(), probar }, attachTo: document.body })
    await flushPromises()
    await botonEnviar(w).trigger('click')
    await flushPromises()
    expect(w.find('pre.pr-cuerpo').text()).toBe('{\n  "a": 1\n}')
    expect(w.text()).toContain('Respuesta cortada en 256 KB')
    w.unmount()

    probar = vi.fn().mockRejectedValue(new ApiError(429, 'Ya hay una prueba en curso'))
    const w2 = mount(EntornosProbador, { props: { entorno: entorno(), probar }, attachTo: document.body })
    await flushPromises()
    await botonEnviar(w2).trigger('click')
    await flushPromises()
    expect(w2.find('.pr-error').text()).toBe('Ya hay una prueba en curso')
    w2.unmount()
  })

  it('cerrar y reabrir resetea ruta; localStorage no se usa', async () => {
    const spy = vi.spyOn(Storage.prototype, 'setItem')
    const probar = vi.fn().mockResolvedValue(resultadoOk())
    const Parent = defineComponent({
      components: { EntornosProbador },
      template: '<EntornosProbador v-if="open" :entorno="e" :probar="probar" @cerrar="open = false" />',
      setup() {
        const open = ref(true)
        return { open, e: entorno(), probar }
      },
    })
    const w = mount(Parent, { attachTo: document.body })
    await flushPromises()
    await w.find('#pr-ruta').setValue('/cambio')
    await w.findAll('button').find((b) => b.text() === 'Cerrar')!.trigger('click')
    await flushPromises()
    w.vm.open = true
    await flushPromises()
    expect((w.find('#pr-ruta').element as HTMLInputElement).value).toBe('/')
    expect(spy).not.toHaveBeenCalled()
    spy.mockRestore()
    w.unmount()
  })
})

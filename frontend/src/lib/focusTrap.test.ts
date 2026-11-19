// @vitest-environment jsdom
import { defineComponent, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { useFocusTrap } from './focusTrap'

function harness(extra?: { initial?: () => HTMLElement | null; onEscape?: () => void }) {
  return defineComponent({
    props: { open: { type: Boolean, default: false } },
    setup(props) {
      const panel = ref<HTMLElement | null>(null)
      const onEscape = extra?.onEscape ?? vi.fn()
      const { onKeydown } = useFocusTrap(panel, () => props.open, {
        onEscape,
        initial: extra?.initial,
      })
      return { panel, onKeydown, onEscape }
    },
    template: `
      <div>
        <button type="button" id="opener">Abrir</button>
        <div v-if="open" ref="panel" tabindex="-1" @keydown="onKeydown">
          <button type="button" id="first">Primero</button>
          <button type="button" disabled id="disabled">Off</button>
          <button type="button" id="mid">Medio</button>
          <button type="button" id="last">Último</button>
        </div>
      </div>
    `,
  })
}

describe('useFocusTrap', () => {
  it('al abrir enfoca el primer botón del panel', async () => {
    const w = mount(harness(), { props: { open: false }, attachTo: document.body })
    const opener = w.find('#opener').element as HTMLButtonElement
    opener.focus()
    await w.setProps({ open: true })
    await flushPromises()
    expect(document.activeElement?.id).toBe('first')
    w.unmount()
  })

  it('con initial enfoca ese elemento', async () => {
    const w = mount(harness({ initial: () => document.getElementById('mid') }), { props: { open: false }, attachTo: document.body })
    ;(w.find('#opener').element as HTMLButtonElement).focus()
    await w.setProps({ open: true })
    await flushPromises()
    expect(document.activeElement?.id).toBe('mid')
    w.unmount()
  })

  it('Tab en el último vuelve al primero y Shift+Tab en el primero al último', async () => {
    const w = mount(harness(), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    const panel = w.find('[tabindex="-1"]').element as HTMLElement
    const last = w.find('#last').element as HTMLButtonElement
    last.focus()
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement?.id).toBe('first')
    const first = w.find('#first').element as HTMLButtonElement
    first.focus()
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', shiftKey: true, bubbles: true }))
    expect(document.activeElement?.id).toBe('last')
    w.unmount()
  })

  it('Escape llama a onEscape una vez', async () => {
    const onEscape = vi.fn()
    const w = mount(harness({ onEscape }), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    const panel = w.find('[tabindex="-1"]').element as HTMLElement
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscape).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('al cerrar devuelve el foco al opener', async () => {
    const w = mount(harness(), { props: { open: false }, attachTo: document.body })
    const opener = w.find('#opener').element as HTMLButtonElement
    opener.focus()
    await w.setProps({ open: true })
    await flushPromises()
    await w.setProps({ open: false })
    await flushPromises()
    expect(document.activeElement).toBe(opener)
    w.unmount()
  })

  it('los botones deshabilitados no cuentan', async () => {
    const Comp = defineComponent({
      props: { open: Boolean },
      setup(props) {
        const panel = ref<HTMLElement | null>(null)
        const { onKeydown } = useFocusTrap(panel, () => props.open)
        return { panel, onKeydown }
      },
      template: `
        <div v-if="open" ref="panel" @keydown="onKeydown">
          <button type="button" id="only">Solo</button>
          <button type="button" disabled id="off">Off</button>
        </div>
      `,
    })
    const w = mount(Comp, { props: { open: true }, attachTo: document.body })
    await flushPromises()
    const root = w.find('div').element as HTMLElement
    const only = w.find('#only').element as HTMLButtonElement
    only.focus()
    root.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement?.id).toBe('only')
    w.unmount()
  })

  it('con foco en body Escape en document llama onEscape una vez', async () => {
    const onEscape = vi.fn()
    const w = mount(harness({ onEscape }), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscape).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('con dos trampas abiertas Escape en body llama solo onEscape de la última', async () => {
    const onEscapeA = vi.fn()
    const onEscapeB = vi.fn()
    const wA = mount(harness({ onEscape: onEscapeA }), { props: { open: true }, attachTo: document.body })
    const wB = mount(harness({ onEscape: onEscapeB }), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscapeA).not.toHaveBeenCalled()
    expect(onEscapeB).toHaveBeenCalledOnce()
    wB.unmount()
    wA.unmount()
  })

  it('Escape en el panel no dispara onEscape dos veces', async () => {
    const onEscape = vi.fn()
    const w = mount(harness({ onEscape }), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    const panel = w.find('[tabindex="-1"]').element as HTMLElement
    panel.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscape).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('Tab con foco en body enfoca el primer botón del panel', async () => {
    const w = mount(harness(), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Tab', bubbles: true }))
    expect(document.activeElement?.id).toBe('first')
    w.unmount()
  })

  it('tras cerrar todas Escape en body no llama onEscape', async () => {
    const onEscape = vi.fn()
    const w = mount(harness({ onEscape }), { props: { open: true }, attachTo: document.body })
    await flushPromises()
    await w.setProps({ open: false })
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscape).not.toHaveBeenCalled()
    w.unmount()
  })

  it('con open función y panel siempre montado, cerrar open saca la trampa', async () => {
    const onEscape = vi.fn()
    const openRef = ref(true)
    const Comp = defineComponent({
      setup() {
        const panel = ref<HTMLElement | null>(null)
        const { onKeydown } = useFocusTrap(panel, () => openRef.value, { onEscape })
        return { panel, onKeydown }
      },
      template: `
        <div ref="panel" tabindex="-1" @keydown="onKeydown">
          <button type="button" id="first">Uno</button>
        </div>
      `,
    })
    const w = mount(Comp, { attachTo: document.body })
    await flushPromises()
    openRef.value = false
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscape).not.toHaveBeenCalled()
    openRef.value = true
    await flushPromises()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscape).toHaveBeenCalledOnce()
    w.unmount()
  })

  it('abrir y cerrar en el mismo tick no deja una trampa zombie', async () => {
    const onEscapeZombie = vi.fn()
    const onEscapeLower = vi.fn()
    const openRef = ref(false)
    const Zombie = defineComponent({
      setup() {
        const panel = ref<HTMLElement | null>(null)
        useFocusTrap(panel, openRef, { onEscape: onEscapeZombie })
        return { panel }
      },
      template: '<div ref="panel" tabindex="-1">z</div>',
    })
    const Lower = defineComponent({
      setup() {
        const panel = ref<HTMLElement | null>(null)
        useFocusTrap(panel, () => true, { onEscape: onEscapeLower })
        return { panel }
      },
      template: '<div ref="panel" tabindex="-1">b</div>',
    })
    const wZ = mount(Zombie, { attachTo: document.body })
    const wL = mount(Lower, { attachTo: document.body })
    await flushPromises()
    openRef.value = true
    openRef.value = false
    await flushPromises()
    ;(document.body as HTMLElement).focus()
    document.body.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(onEscapeZombie).not.toHaveBeenCalled()
    expect(onEscapeLower).toHaveBeenCalledOnce()
    wL.unmount()
    wZ.unmount()
  })

  it('con initial en el panel el foco queda en el panel y no en un botón', async () => {
    const Comp = defineComponent({
      props: { open: Boolean },
      setup(props) {
        const panel = ref<HTMLElement | null>(null)
        useFocusTrap(panel, () => props.open, {
          initial: () => panel.value,
        })
        return { panel }
      },
      template: `
        <div v-if="open" ref="panel" tabindex="-1">
          <button type="button" id="first">Primero</button>
        </div>
      `,
    })
    const w = mount(Comp, { props: { open: true }, attachTo: document.body })
    await flushPromises()
    expect(document.activeElement).toBe(w.find('[tabindex="-1"]').element)
    w.unmount()
  })
})

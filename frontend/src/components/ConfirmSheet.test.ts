// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))

const { default: ConfirmSheet } = await import('./ConfirmSheet.vue')

describe('ConfirmSheet foco', () => {
  it('al abrir enfoca Cancelar y no la acción de peligro', async () => {
    mount(ConfirmSheet, {
      props: { open: true, title: '¿Borrar?', confirmLabel: 'Borrar' },
      attachTo: document.body,
    })
    await flushPromises()
    const cancel = document.body.querySelector('button.btn.btn-ghost') as HTMLButtonElement | null
    expect(cancel).toBeTruthy()
    expect(document.activeElement).toBe(cancel)
  })
})

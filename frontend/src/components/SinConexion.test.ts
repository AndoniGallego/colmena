// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const boardState = ref<{ connection: 'live' | 'connecting' | 'reconnecting' }>({ connection: 'live' })

vi.mock('../state/app', () => ({ boardState }))

const { default: SinConexion } = await import('./SinConexion.vue')

describe('SinConexion', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date(1_000_000))
    boardState.value.connection = 'live'
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('muestra el texto tras reconexión prolongada', async () => {
    boardState.value.connection = 'reconnecting'
    const w = mount(SinConexion)
    await flushPromises()
    expect(w.text()).not.toContain('Sin conexión, reintentando…')
    vi.advanceTimersByTime(3000)
    await flushPromises()
    expect(w.text()).toContain('Sin conexión, reintentando…')
  })
})

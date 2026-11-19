// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/types'

const login = vi.fn()

vi.mock('../state/app', () => ({ login: (...a: unknown[]) => login(...a) }))
vi.mock('../motion', () => ({
  gsap: {
    from() {},
    fromTo() {},
    timeline: () => ({ to() {}, from() {}, fromTo() {}, add() {} }),
    utils: { selector: () => () => [] },
  },
  haptic: () => {},
  isSoft: () => true,
  SplitText: { create: () => ({ chars: [], revert() {} }) },
  unlocked: { value: false },
  useGsap: () => ({ run: (fn: () => void) => fn() }),
  vMagnetic: () => {},
}))
vi.mock('./Icon.vue', () => ({ default: { template: '<i />' } }))
vi.mock('./BrandLockup.vue', () => ({ default: { template: '<span class="brand" />' } }))

const { default: LoginScreen } = await import('./LoginScreen.vue')

describe('LoginScreen bloqueo', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    login.mockReset()
    login.mockRejectedValue(new ApiError(429, 'x', 90))
  })

  afterEach(() => {
    vi.useRealTimers()
    document.body.innerHTML = ''
  })

  it('role="alert" no incluye la cuenta regresiva', async () => {
    const w = mount(LoginScreen, { attachTo: document.body })
    await w.find('input').setValue('1234')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    const alert = w.find('[role="alert"]')
    expect(alert.text()).toBe('Demasiados intentos.')
    expect(alert.text()).not.toMatch(/\d+\s*s/)
    w.unmount()
  })

  it('la cuenta regresiva está aria-hidden', async () => {
    const w = mount(LoginScreen, { attachTo: document.body })
    await w.find('input').setValue('1234')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    const hidden = w.find('[aria-hidden="true"] .mono')
    expect(hidden.exists()).toBe(true)
    expect(hidden.text()).toMatch(/\d+/)
    w.unmount()
  })

  it('el texto sr-only no cambia al avanzar 1 s', async () => {
    const w = mount(LoginScreen, { attachTo: document.body })
    await w.find('input').setValue('1234')
    await w.find('form').trigger('submit.prevent')
    await flushPromises()
    const sr = w.find('.sr-only')
    const antes = sr.text()
    vi.advanceTimersByTime(1000)
    await flushPromises()
    expect(sr.text()).toBe(antes)
    w.unmount()
  })
})

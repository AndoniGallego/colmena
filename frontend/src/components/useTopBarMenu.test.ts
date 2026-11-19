import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useTopBarMenu } from './useTopBarMenu'

describe('useTopBarMenu', () => {
  const revokeAllSessions = vi.fn(async () => true)

  beforeEach(() => {
    revokeAllSessions.mockClear()
    revokeAllSessions.mockResolvedValue(true)
  })

  it('revoke cierra overlays si la sesión se revoca', async () => {
    const m = useTopBarMenu(revokeAllSessions)
    m.menuOpen.value = true
    m.menuConfirming.value = true
    m.salirPopOpen.value = true
    await m.revoke()
    expect(revokeAllSessions).toHaveBeenCalledTimes(1)
    expect(m.menuOpen.value).toBe(false)
    expect(m.menuConfirming.value).toBe(false)
    expect(m.salirPopOpen.value).toBe(false)
    expect(m.revoking.value).toBe(true)
  })

  it('no cierra overlays si revoke falla', async () => {
    revokeAllSessions.mockResolvedValueOnce(false)
    const m = useTopBarMenu(revokeAllSessions)
    m.menuOpen.value = true
    m.salirPopOpen.value = true
    await m.revoke()
    expect(m.menuOpen.value).toBe(true)
    expect(m.salirPopOpen.value).toBe(true)
    expect(m.revoking.value).toBe(false)
  })

  it('Escape cierra menú y popover de salir', () => {
    const m = useTopBarMenu(revokeAllSessions)
    m.menuOpen.value = true
    m.menuConfirming.value = true
    m.salirPopOpen.value = true
    m.onKey({ key: 'Escape' } as KeyboardEvent)
    expect(m.menuOpen.value).toBe(false)
    expect(m.menuConfirming.value).toBe(false)
    expect(m.salirPopOpen.value).toBe(false)
  })

  it('pointerdown fuera cierra popover de salir', () => {
    const m = useTopBarMenu(revokeAllSessions)
    const fakeEl = { contains: () => false } as unknown as HTMLElement
    m.salirBtnRef.value = fakeEl
    m.salirPopRef.value = fakeEl
    m.salirPopOpen.value = true
    m.onDoc({ target: {} } as unknown as Event)
    expect(m.salirPopOpen.value).toBe(false)
  })
})

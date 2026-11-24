import { describe, expect, it } from 'vitest'
import { claimReload, IDLE_MS, isStale, isWorking, reloadDecision, tracked, type UpdateContext } from './update'

const ctx = (over: Partial<UpdateContext> = {}): UpdateContext => ({
  own: 'aaa', remote: 'bbb', trigger: 'notice', typing: false, working: false, visible: true, idleMs: 0, ...over,
})

describe('isStale', () => {
  it('solo cuando ambos builds se conocen y difieren', () => {
    expect(isStale('aaa', 'bbb')).toBe(true)
    expect(isStale('aaa', 'aaa')).toBe(false)
    expect(isStale('aaa', '')).toBe(false)
    expect(isStale('dev', 'bbb')).toBe(false)
    expect(isStale('', 'bbb')).toBe(false)
  })
})

describe('reloadDecision', () => {
  it('con una reunión en curso nunca recarga: espera a que termine', () => {
    for (const trigger of ['visible', 'notice', 'idle'] as const) {
      expect(reloadDecision(ctx({ trigger, meeting: true, idleMs: 9e9 }))).toBe('wait')
      expect(reloadDecision(ctx({ trigger, meeting: true, visible: false }))).toBe('wait')
    }
    expect(reloadDecision(ctx({ trigger: 'idle', meeting: false, idleMs: 9e9 }))).toBe('reload')
  })

  it('no hace nada si el build es el mismo', () => {
    expect(reloadDecision(ctx({ remote: 'aaa', trigger: 'visible' }))).toBe('none')
  })

  it('al volver a primer plano recarga', () => {
    expect(reloadDecision(ctx({ trigger: 'visible' }))).toBe('reload')
  })

  it('con la app a la vista espera a que haya inactividad', () => {
    expect(reloadDecision(ctx({ idleMs: IDLE_MS - 1 }))).toBe('wait')
    expect(reloadDecision(ctx({ trigger: 'idle', idleMs: IDLE_MS }))).toBe('reload')
  })

  it('nunca recarga escribiendo ni con un envío o subida en curso', () => {
    for (const trigger of ['visible', 'notice', 'idle'] as const) {
      expect(reloadDecision(ctx({ trigger, typing: true, idleMs: 9e9 }))).toBe('wait')
      expect(reloadDecision(ctx({ trigger, working: true, idleMs: 9e9 }))).toBe('wait')
    }
    expect(reloadDecision(ctx({ visible: false, typing: true }))).toBe('wait')
  })

  it('oculta y sin trabajo recarga sin esperar', () => {
    expect(reloadDecision(ctx({ visible: false }))).toBe('reload')
  })
})

describe('tracked', () => {
  it('marca trabajo mientras dura y lo suelta aunque falle', async () => {
    let release!: () => void
    const p = tracked(new Promise<void>((res) => (release = res)))
    expect(isWorking()).toBe(true)
    release()
    await p
    expect(isWorking()).toBe(false)
    await expect(tracked(Promise.reject(new Error('x')))).rejects.toThrow('x')
    expect(isWorking()).toBe(false)
  })
})

describe('claimReload', () => {
  const memory = () => {
    const m = new Map<string, string>()
    return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }
  }

  it('recarga una sola vez por build', () => {
    const store = memory()
    expect(claimReload('bbb', store)).toBe(true)
    expect(claimReload('bbb', store)).toBe(false)
    expect(claimReload('ccc', store)).toBe(true)
  })

  it('sin storage utilizable igual deja recargar', () => {
    const broken = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') } }
    expect(claimReload('bbb', broken)).toBe(true)
  })
})

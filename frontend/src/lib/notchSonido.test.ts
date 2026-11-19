import { describe, expect, it, vi } from 'vitest'
import { sonarTeToca } from './notchSonido'

type FakeOsc = { freq: number; stopAt: number; type: string; connect: ReturnType<typeof vi.fn> }

function fakeCtx(state: AudioContextState = 'running') {
  const gains: number[] = []
  const oscs: FakeOsc[] = []
  const resume = vi.fn(async () => {
    ctx.state = 'running'
  })
  const ctx = {
    state,
    resume,
    currentTime: 0,
    destination: {},
    gains,
    oscs,
    createOscillator() {
      const o = {
        freq: 0,
        stopAt: 0,
        type: '',
        connect: vi.fn(),
        frequency: { setValueAtTime(_t: number, v: number) {} },
        start: vi.fn(),
        stop: vi.fn(),
      }
      o.frequency.setValueAtTime = (v: number) => {
        o.freq = v
      }
      o.stop = vi.fn((at: number) => {
        o.stopAt = at
      })
      oscs.push(o as FakeOsc)
      return o as unknown as OscillatorNode
    },
    createGain() {
      const g = {
        gain: {
          setValueAtTime(v: number) {
            gains.push(v)
          },
          linearRampToValueAtTime(v: number) {
            gains.push(v)
          },
          exponentialRampToValueAtTime(v: number) {
            gains.push(v)
          },
        },
        connect: vi.fn(),
      }
      return g as unknown as GainNode
    },
  }
  return ctx as typeof ctx & AudioContext
}

describe('lib/notchSonido', () => {
  it('dos notas cortas y suaves', () => {
    const ctx = fakeCtx()
    expect(sonarTeToca(() => ctx)).toBe(true)
    expect(ctx.oscs.map((o) => o.freq)).toEqual([660, 990])
    expect(Math.max(...ctx.gains)).toBeLessThanOrEqual(0.05)
    expect(Math.max(...ctx.oscs.map((o) => o.stopAt))).toBeLessThanOrEqual(0.35)
  })

  it('sin audio no rompe', () => {
    expect(sonarTeToca(() => null)).toBe(false)
  })

  it('despierta un contexto suspendido', async () => {
    const ctx = fakeCtx('suspended')
    expect(sonarTeToca(() => ctx)).toBe(true)
    expect(ctx.resume).toHaveBeenCalled()
  })
})

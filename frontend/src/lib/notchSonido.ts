let ctx: AudioContext | null = null

export function sonarTeToca(crear?: () => AudioContext | null): boolean {
  if (crear) {
    const next = crear()
    if (!next) return false
    ctx = next
  } else if (!ctx) {
    if (typeof AudioContext === 'undefined') return false
    ctx = new AudioContext()
  }
  if (!ctx) return false
  if (ctx.state === 'suspended') void ctx.resume()

  const t = ctx.currentTime
  const notas = [660, 990]
  for (let i = 0; i < notas.length; i++) {
    const osc = ctx.createOscillator()
    const gain = ctx.createGain()
    osc.type = 'sine'
    const t0 = t + i * 0.1
    osc.frequency.setValueAtTime(notas[i]!, t0)
    gain.gain.setValueAtTime(0, t0)
    gain.gain.linearRampToValueAtTime(0.05, t0 + 0.01)
    gain.gain.exponentialRampToValueAtTime(0.0001, t0 + 0.12)
    osc.connect(gain)
    gain.connect(ctx.destination)
    osc.start(t0)
    osc.stop(t0 + 0.12)
  }
  return true
}

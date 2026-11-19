import { computed, onUnmounted, ref, watchEffect } from 'vue'
import { gsap } from 'gsap'
import { Flip } from 'gsap/Flip'
import { CustomEase } from 'gsap/CustomEase'
import { Physics2DPlugin } from 'gsap/Physics2DPlugin'
import { SplitText } from 'gsap/SplitText'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'
import { MotionPathPlugin } from 'gsap/MotionPathPlugin'
import { loadMotion, saveMotion, type MotionPref } from '../lib/storage'

gsap.registerPlugin(Flip, CustomEase, Physics2DPlugin, SplitText, DrawSVGPlugin, MotionPathPlugin)

CustomEase.create('orq.spring', 'M0,0 C0.12,0.62 0.2,1.1 0.38,1.08 0.52,1.06 0.62,0.99 0.74,0.995 0.84,1 0.92,1 1,1')
CustomEase.create('orq.sheet', '0.32,0.72,0,1')
CustomEase.create('orq.snap', 'M0,0 C0.2,0 0.08,1 1,1')
CustomEase.create('orq.pop', 'M0,0 C0.1,0.9 0.2,1.25 0.42,1.12 0.6,1.02 0.76,0.985 1,1')

export { gsap, Flip, SplitText }
export { animateViewEnter, viewEnterPreset } from '../lib/viewEnter'

const pref = ref<MotionPref>(loadMotion())
const sysReduced = ref(false)

gsap.matchMedia().add('(prefers-reduced-motion: reduce)', () => {
  sysReduced.value = true
  return () => {
    sysReduced.value = false
  }
})

export const motionPref = pref
/** Soft mode: short fades, no travel, no particles. Driven by the user toggle or the OS setting. */
export const soft = computed(() => pref.value === 'soft' || sysReduced.value)
export const systemReduced = computed(() => sysReduced.value)
export const isSoft = () => soft.value

export function setMotion(p: MotionPref) {
  pref.value = p
  saveMotion(p)
}

if (typeof document !== 'undefined') {
  const root = document.documentElement
  watchEffect(() => (root.dataset.motion = soft.value ? 'soft' : 'full'))
  const vis = () => root.toggleAttribute('data-hidden', document.hidden)
  document.addEventListener('visibilitychange', vis)
  vis()
}

/** Per-component GSAP scope: everything created through `run` dies with the component. */
export function useGsap() {
  const ctx = gsap.context(() => {})
  onUnmounted(() => ctx.kill())
  return {
    run<T>(fn: () => T): T {
      let out!: T
      ctx.add(() => {
        out = fn()
      })
      return out
    },
    ctx,
  }
}

export const finePointer = () => typeof window !== 'undefined' && window.matchMedia('(hover: hover) and (pointer: fine)').matches

export function haptic(pattern: number | number[]) {
  try {
    navigator.vibrate?.(pattern)
  } catch {
    /* not supported */
  }
}

// ---------- fx layer ----------
let layer: HTMLDivElement | null = null
function fxLayer() {
  if (!layer || !layer.isConnected) {
    layer = document.createElement('div')
    layer.className = 'fx-layer'
    layer.setAttribute('aria-hidden', 'true')
    document.body.append(layer)
  }
  return layer
}

type Origin = Element | { x: number; y: number }
function point(o: Origin) {
  if ('getBoundingClientRect' in o) {
    const r = o.getBoundingClientRect()
    return { x: r.left + r.width / 2, y: r.top + r.height / 2 }
  }
  return o
}

const css = (name: string) => getComputedStyle(document.documentElement).getPropertyValue(name).trim()
const rnd = gsap.utils.random

export interface BurstOptions {
  count?: number
  colors?: string[]
  power?: number
  /** angle range in degrees, 0 = right, -90 = up */
  angle?: [number, number]
  gravity?: number
  confetti?: boolean
}

/** Particle burst at a point; transform/opacity only, nodes are removed when done. */
export function burst(origin: Origin, o: BurstOptions = {}) {
  if (soft.value || typeof document === 'undefined' || document.hidden) return
  const { x, y } = point(origin)
  const L = fxLayer()
  const colors = o.colors ?? [css('--accent'), css('--accent'), css('--st-done'), css('--st-working')]
  const n = o.count ?? 22
  const [a0, a1] = o.angle ?? [-180, 0]
  const power = o.power ?? 1
  for (let i = 0; i < n; i++) {
    const el = document.createElement('i')
    const rect = o.confetti && i % 3 !== 0
    el.className = rect ? 'fx-p fx-r' : 'fx-p'
    el.style.background = colors[i % colors.length]
    L.append(el)
    const size = rect ? 1 : rnd(0.5, 1.15)
    gsap.set(el, { x, y, xPercent: -50, yPercent: -50, scale: size, rotation: rnd(0, 360) })
    const life = rnd(0.8, 1.4)
    gsap.to(el, {
      duration: life,
      physics2D: { velocity: rnd(160, 440) * power, angle: rnd(a0, a1), gravity: o.gravity ?? 820 },
      rotation: `+=${rnd(-260, 260)}`,
      onComplete: () => el.remove(),
    })
    gsap.to(el, { opacity: 0, scale: size * 0.4, duration: life * 0.45, delay: life * 0.55, ease: 'power2.in' })
  }
}

/** Expanding ring (shockwave) at a point. */
export function ring(origin: Origin, color = css('--accent'), size = 60) {
  if (soft.value || typeof document === 'undefined' || document.hidden) return
  const { x, y } = point(origin)
  const el = document.createElement('i')
  el.className = 'fx-ring'
  el.style.borderColor = color
  el.style.width = el.style.height = `${size}px`
  fxLayer().append(el)
  gsap.fromTo(
    el,
    { x, y, xPercent: -50, yPercent: -50, scale: 0.2, opacity: 0.9 },
    { scale: 1.6, opacity: 0, duration: 0.75, ease: 'power2.out', onComplete: () => el.remove() },
  )
}

/** Window in which sibling mounts share a cascade; returns this mount's delay. */
let cascadeAt = 0
let cascadeN = 0
export function cascadeDelay(step = 0.045, cap = 10) {
  const t = performance.now()
  if (t - cascadeAt > 60) cascadeN = 0
  cascadeAt = t
  return Math.min(cascadeN++, cap) * step
}

/** Ceremony flag: the shell plays its power-on sweep only right after a PIN unlock. */
export const unlocked = ref(false)

/** Bumped when a handoff is confirmed; the brand mark answers with a hop across its ring. */
export const brandHop = ref(0)

/** Magnetic pull towards the pointer for primary buttons (fine pointers only). */
export const vMagnetic = {
  mounted(el: HTMLElement & { _mag?: () => void }, binding: { value?: number }) {
    if (!finePointer()) return
    const k = binding.value ?? 0.28
    const xTo = gsap.quickTo(el, 'x', { duration: 0.45, ease: 'power3.out' })
    const yTo = gsap.quickTo(el, 'y', { duration: 0.45, ease: 'power3.out' })
    const move = (e: PointerEvent) => {
      if (soft.value) return
      const r = el.getBoundingClientRect()
      xTo((e.clientX - (r.left + r.width / 2)) * k)
      yTo((e.clientY - (r.top + r.height / 2)) * k)
    }
    const leave = () => {
      gsap.to(el, { x: 0, y: 0, duration: 0.3, ease: 'power3.out', overwrite: 'auto' })
    }
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', leave)
    el._mag = () => {
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', leave)
      gsap.killTweensOf(el)
    }
  },
  unmounted(el: HTMLElement & { _mag?: () => void }) {
    el._mag?.()
  },
}

/** Pointer-tracked spotlight: writes --mx/--my on the hovered `selector` inside the host. */
export const vSpotlight = {
  mounted(el: HTMLElement & { _spot?: () => void }, binding: { value: string }) {
    if (!finePointer()) return
    let raf = 0
    let last: PointerEvent | null = null
    let cur: HTMLElement | null = null
    const paint = () => {
      raf = 0
      if (!last) return
      const t = (last.target as HTMLElement | null)?.closest<HTMLElement>(binding.value)
      if (cur && cur !== t) cur.removeAttribute('data-spot')
      cur = t ?? null
      if (!cur) return
      const r = cur.getBoundingClientRect()
      cur.style.setProperty('--mx', `${last.clientX - r.left}px`)
      cur.style.setProperty('--my', `${last.clientY - r.top}px`)
      cur.setAttribute('data-spot', '')
    }
    const move = (e: PointerEvent) => {
      last = e
      if (!raf) raf = requestAnimationFrame(paint)
    }
    const leave = () => {
      cur?.removeAttribute('data-spot')
      cur = null
    }
    el.addEventListener('pointermove', move, { passive: true })
    el.addEventListener('pointerleave', leave)
    el._spot = () => {
      cancelAnimationFrame(raf)
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', leave)
    }
  },
  unmounted(el: HTMLElement & { _spot?: () => void }) {
    el._spot?.()
  },
}

import { gsap } from 'gsap'
import type { EstadoCelda } from '../../lib/notchCeldas'

export interface MarkProps {
  size?: number
  working?: boolean
  attention?: boolean
  live?: boolean
  intro?: boolean
  /** Sesiones trabajando ahora: cuántas celdas se encienden. */
  active?: number
  /** Versión cargador: un ciclo continuo que no depende del estado. */
  loader?: boolean
  /** Modo notch: estado visual por celda del anillo. */
  cells?: readonly EstadoCelda[]
}

export const MARK_DEFAULTS = { size: 28, live: true, intro: true, loader: false } as const

/** Celdas que corresponde encender, entre 0 y `max`. */
export function litCount(p: MarkProps, max: number): number {
  if (p.loader || p.live === false) return 0
  const n = Math.max(p.active ?? 0, p.working ? 1 : 0)
  return Math.min(max, Math.max(0, Math.round(n)))
}

export function markMode(p: MarkProps): 'loader' | 'attention' | 'working' | 'idle' {
  return p.loader ? 'loader' : p.attention ? 'attention' : p.working || (p.active ?? 0) > 0 ? 'working' : 'idle'
}

/** Cometa que da vueltas por las celdas: cada una se enciende y se apaga con estela, sin costura entre vueltas. */
export function comet(els: Element[], step: number, dur = 0.9, floor = 0.06) {
  const tl = gsap.timeline()
  const gap = Math.max(0, els.length * step - dur)
  els.forEach((el, i) => {
    tl.fromTo(el, { opacity: 1, scale: 1.06 }, { opacity: floor, scale: 1, duration: dur, ease: 'power1.in', repeat: -1, repeatDelay: gap }, i * step)
  })
  return tl
}

/** Respiración desfasada: las celdas encendidas laten de a una, como una ola lenta. */
export function breathe(els: Element[]) {
  return gsap.to(els, { opacity: 0.74, duration: 1.7, ease: 'sine.inOut', stagger: { each: 0.32, repeat: -1, yoyo: true } })
}

/** Latido de alerta: el elemento salta y una onda se expande. */
export function beat(el: Element, wave: Element, peak = 1.14) {
  return gsap
    .timeline({ repeat: -1, repeatDelay: 0.6 })
    .fromTo(el, { scale: 1 }, { scale: peak, duration: 0.18, ease: 'power2.out' })
    .to(el, { scale: 1, duration: 0.7, ease: 'elastic.out(1.1, 0.4)' })
    .fromTo(wave, { scale: 1, opacity: 0.8 }, { scale: 2.1, opacity: 0, duration: 1.1, ease: 'power2.out' }, 0)
}

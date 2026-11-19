import type { gsap as GsapType } from 'gsap'

export type ViewEnterRun = <T>(fn: () => T) => T

export interface ViewEnterOptions {
  y?: number
  duration?: number
  stagger?: number
  delay?: number
  ease?: string
}

const DEFAULTS: Required<ViewEnterOptions> = {
  y: 12,
  duration: 0.45,
  stagger: 0.04,
  delay: 0,
  ease: 'power3.out',
}

/** Shared list entrance: one curve/duration/stagger; no-op when soft or empty. */
export function animateViewEnter(
  gsap: typeof GsapType,
  run: ViewEnterRun,
  targets: Element[] | NodeListOf<Element> | null | undefined,
  soft: boolean,
  opts: ViewEnterOptions = {},
) {
  const els = targets ? [...targets] : []
  if (!els.length || soft) return
  const o = { ...DEFAULTS, ...opts }
  gsap.killTweensOf(els)
  run(() =>
    gsap.fromTo(els, { y: o.y, opacity: 0 }, {
      y: 0,
      opacity: 1,
      duration: o.duration,
      ease: o.ease,
      stagger: o.stagger,
      delay: o.delay,
      clearProps: 'transform,opacity',
    }),
  )
}

export function viewEnterPreset(soft: boolean): ViewEnterOptions | null {
  if (soft) return null
  return { ...DEFAULTS }
}

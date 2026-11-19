import { onBeforeUnmount, nextTick, type Ref, watch } from 'vue'
import { gsap, isSoft } from '../motion'

const GRAB = '.sheet-grip, .sheet-title'
const SKIP = 'button, a, input, select, textarea, label'
const CLOSE_RATIO = 0.25
const CLOSE_VELOCITY = 0.5
const STALE_MS = 80
const LEAVING = '[class*="-leave-active"]'

const rubber = (dy: number) => -Math.sqrt(-dy) * 2

/** Arrastrar hacia abajo (o hacia arriba con direccion 'arriba') desde la barrita o el título cierra la hoja; si no alcanza, vuelve. */
export function useSheetSwipe(
  panel: Ref<HTMLElement | null>,
  onClose: () => void,
  opts: { direccion?: 'abajo' | 'arriba'; activo?: () => boolean } = {},
) {
  const sign = opts.direccion === 'arriba' ? -1 : 1
  let el: HTMLElement | null = null
  let id = -1
  let startY = 0
  let dy = 0
  let lastY = 0
  let lastT = 0
  let v = 0
  let back: gsap.core.Tween | null = null
  let setY: ((y: number) => void) | null = null

  function shown(raw: number) {
    return raw >= 0 ? raw : rubber(raw)
  }

  function down(e: PointerEvent) {
    if (!el || id !== -1 || e.pointerType === 'mouse' || opts.activo?.() === false) return
    const t = e.target instanceof Element ? e.target : null
    if (!t?.closest(GRAB) || t.closest(SKIP)) return
    id = e.pointerId
    startY = lastY = e.clientY
    lastT = e.timeStamp
    dy = 0
    v = 0
    back?.kill()
    back = null
    const q = gsap.quickSetter(el, 'y', 'px') as (y: number) => void
    setY = (y) => q(y * sign)
    try {
      el.setPointerCapture?.(id)
    } catch {
      /* captura no disponible */
    }
  }

  function move(e: PointerEvent) {
    if (!el || e.pointerId !== id) return
    dy = (e.clientY - startY) * sign
    const dt = e.timeStamp - lastT
    if (dt > 0) v = ((e.clientY - lastY) * sign) / dt
    lastY = e.clientY
    lastT = e.timeStamp
    setY?.(shown(dy))
  }

  function settle(target: HTMLElement) {
    if (isSoft()) {
      gsap.set(target, { y: 0 })
      return
    }
    back = gsap.to(target, { y: 0, duration: 0.3, ease: 'orq.sheet', clearProps: 'y' })
  }

  function keepLeaving(target: HTMLElement) {
    if (!isSoft()) gsap.to(target, { y: target.offsetHeight * sign, duration: 0.2, ease: 'power2.in' })
  }

  function up(e: PointerEvent) {
    if (!el || e.pointerId !== id) return
    const target = el
    id = -1
    const cancelled = e.type === 'pointercancel'
    if (e.timeStamp - lastT > STALE_MS) v = 0
    const alto = target.offsetHeight || 1
    const cierra = !cancelled && dy > 0 && (dy > alto * CLOSE_RATIO || v > CLOSE_VELOCITY)
    gsap.set(target, { y: shown(dy) * sign })
    if (!cierra) return settle(target)
    onClose()
    void nextTick(() => {
      if (!target.isConnected || gsap.isTweening?.(target)) return
      if (target.closest(LEAVING)) keepLeaving(target)
      else settle(target)
    })
  }

  function attach(next: HTMLElement | null) {
    detach()
    el = next
    el?.addEventListener('pointerdown', down)
    el?.addEventListener('pointermove', move)
    el?.addEventListener('pointerup', up)
    el?.addEventListener('pointercancel', up)
  }
  function detach() {
    el?.removeEventListener('pointerdown', down)
    el?.removeEventListener('pointermove', move)
    el?.removeEventListener('pointerup', up)
    el?.removeEventListener('pointercancel', up)
    el = null
    setY = null
    id = -1
  }

  watch(panel, attach, { immediate: true, flush: 'post' })
  onBeforeUnmount(detach)
}

import { nextTick } from 'vue'
import { Flip, gsap, isSoft } from '../motion'

/** La tarjeta se pliega en celda hexagonal mientras vuela al frasco de Hechas. */
const HEX = 'polygon(50% 0%, 100% 25%, 100% 75%, 50% 100%, 0% 75%, 0% 25%)'
const RECT = 'polygon(50% 0%, 100% 0%, 100% 100%, 50% 100%, 0% 100%, 0% 0%)'
const FUNDIDO = 0.15
const TOPE_VUELO = 120

const q = (el: Element, sel: string) => el.querySelector(sel)
const qa = (el: Element, sel: string) => [...el.querySelectorAll(sel)]

/** Nota nueva (o que vuelve sellada): cae con resorte y un destello lima que se apaga. */
export function entrarNota(el: Element): void {
  gsap.killTweensOf(el)
  if (isSoft()) {
    gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: FUNDIDO, clearProps: 'opacity' })
    return
  }
  gsap.fromTo(
    el,
    { y: -70, scale: 0.3, rotation: -60, opacity: 0 },
    { y: 0, scale: 1, rotation: 0, opacity: 1, duration: 1, ease: 'elastic.out(1,.55)', delay: 0.15, clearProps: 'transform,opacity' },
  )
  const brillo = q(el, '.nota-brillo')
  if (brillo) gsap.fromTo(brillo, { opacity: 1 }, { opacity: 0, duration: 1.2, delay: 0.9 })
}

const CASCADA_MAX = 12

/** Primera carga de la vista: las primeras tarjetas entran escalonadas; con movimiento suave, solo fundido. */
export function cascadaEntrada(tarjetas: Element[]): void {
  const els = tarjetas.slice(0, CASCADA_MAX)
  if (!els.length) return
  gsap.killTweensOf(els)
  if (isSoft()) {
    gsap.fromTo(els, { opacity: 0 }, { opacity: 1, duration: FUNDIDO, clearProps: 'opacity' })
    return
  }
  gsap.fromTo(
    els,
    { opacity: 0, y: 12, scale: 0.96 },
    { opacity: 1, y: 0, scale: 1, duration: 0.32, stagger: 0.035, ease: 'power2.out', clearProps: 'transform,opacity' },
  )
}

/** Rebote corto del hexágono contador de hechas. */
export function rebotarContador(hex: Element | null): void {
  if (!hex || isSoft()) return
  gsap.to(hex, { scale: 1.12, duration: 0.14, yoyo: true, repeat: 1, ease: 'power2.out', clearProps: 'transform' })
}

/** Tocar una tarjeta en el celu: se levanta un poco con sombra. Resuelve cuando terminó (de inmediato con movimiento suave). */
export function levantarTarjeta(el: Element): Promise<void> {
  if (isSoft()) return Promise.resolve()
  const sombra = q(el, '.nota-sombra')
  gsap.killTweensOf(el)
  if (sombra) gsap.to(sombra, { opacity: 1, duration: 0.14, ease: 'power2.out' })
  return new Promise((ok) => {
    gsap.to(el, { scale: 1.03, duration: 0.14, ease: 'power2.out', onComplete: () => ok(), onInterrupt: () => ok() })
  })
}

/** La tarjeta levantada vuelve a su lugar. */
export function bajarTarjeta(el: Element): void {
  const sombra = q(el, '.nota-sombra')
  if (sombra) gsap.to(sombra, { opacity: 0, duration: 0.2, clearProps: 'opacity' })
  gsap.to(el, { scale: 1, duration: 0.2, ease: 'power2.out', clearProps: 'transform' })
}

function limpiar(el: Element) {
  const partes = [q(el, '.nota-miel'), q(el, '.nota-tilde-marca'), ...qa(el, '.nota-ala')].filter(Boolean) as Element[]
  gsap.killTweensOf([el, ...partes])
  gsap.set(partes, { clearProps: 'transform,opacity,clipPath' })
  el.classList.remove('melada')
}

/**
 * Completar un recordatorio: la miel sube desde abajo, se tilda, aletea como una abeja y vuela,
 * plegada en celda, al frasco de Hechas. Resuelve con la tarjeta invisible y limpia, lista para
 * reaparecer sellada. Con movimiento suave, solo un fundido corto.
 */
export function completarNota(el: Element, destino: Element): Promise<void> {
  if (isSoft()) {
    return new Promise((ok) => {
      gsap.to(el, { opacity: 0, duration: FUNDIDO, onComplete: () => ok() })
    })
  }
  const miel = q(el, '.nota-miel')
  const marca = q(el, '.nota-tilde-marca')
  const alas = qa(el, '.nota-ala')
  const alto = (el as HTMLElement).offsetHeight || 120

  return new Promise((ok) => {
    let clon: HTMLElement | null = null
    const tl = gsap.timeline({
      onComplete: () => {
        clon?.remove()
        limpiar(el)
        gsap.set(el, { clearProps: 'transform', opacity: 0 })
        ok()
      },
    })
    tl.to(el, { scale: 0.94, duration: 0.1, yoyo: true, repeat: 1, ease: 'power2.out' })
    if (miel) {
      tl.fromTo(miel, { y: 0, rotation: 0 }, { y: -alto * 1.6, rotation: 160, duration: 1.6, ease: 'power1.inOut' })
      tl.call(() => el.classList.add('melada'), [], '-=0.8')
    }
    if (marca) tl.fromTo(marca, { clipPath: 'inset(0% 100% 0% 0%)' }, { clipPath: 'inset(0% 0% 0% 0%)', duration: 0.35, ease: 'power2.out' }, '-=0.15')
    if (alas.length) {
      tl.to(alas, { opacity: 1, duration: 0.15 }, '+=0.15')
      tl.to(alas, { scaleY: 0.25, duration: 0.055, repeat: 13, yoyo: true, ease: 'sine.inOut' }, '<')
    }
    tl.to(el, { keyframes: { rotation: [0, -5, 4, -3, 2, 0], y: [0, -6, -14, -10, -18, -16] }, duration: 0.8, ease: 'none' }, '<')
    // El vuelo va en un clon fijo para que el scroll de la vista no lo recorte.
    tl.call(() => {
      gsap.set(el, { rotation: 0 })
      const r = el.getBoundingClientRect()
      const d = destino.getBoundingClientRect()
      clon = el.cloneNode(true) as HTMLElement
      clon.classList.add('nota-vuelo')
      clon.setAttribute('aria-hidden', 'true')
      clon.setAttribute('inert', '')
      Object.assign(clon.style, {
        position: 'fixed',
        left: `${r.left}px`,
        top: `${r.top}px`,
        width: `${r.width}px`,
        height: `${r.height}px`,
        margin: '0',
        zIndex: '60',
        pointerEvents: 'none',
        transform: 'none',
      })
      document.body.append(clon)
      gsap.set(el, { opacity: 0 })
      const dx = d.left + d.width / 2 - (r.left + r.width / 2)
      const dy = d.top + d.height / 2 - (r.top + r.height / 2)
      const alasClon = qa(clon, '.nota-ala')
      if (alasClon.length) gsap.to(alasClon, { scaleY: 0.25, duration: 0.055, repeat: 11, yoyo: true, ease: 'sine.inOut' })
      gsap
        .timeline()
        .fromTo(clon, { clipPath: RECT }, { clipPath: HEX, duration: 0.35, ease: 'power2.inOut' }, 0)
        .to(clon, { x: dx, y: dy, scale: 0.16, rotation: 24, duration: 0.7, ease: 'power2.in' }, 0)
        .to(clon, { opacity: 0, duration: 0.1 })
        .to(destino, { scale: 1.18, duration: 0.12, yoyo: true, repeat: 1 }, '<')
    })
    tl.to({}, { duration: 0.95 })
  })
}

/**
 * Antes de sacar tarjetas por un filtro: se encogen girando, como en la maqueta. En el celu se
 * achican y funden sin girar; con movimiento suave, solo se funden.
 */
export function despedir(els: Element[], celu = false): Promise<void> {
  if (!els.length) return Promise.resolve()
  const vars = isSoft() ? { opacity: 0, duration: FUNDIDO } : celu ? { opacity: 0, scale: 0.85, duration: 0.22, ease: 'power2.in' } : { opacity: 0, scale: 0.2, rotation: 60, duration: 0.3, ease: 'power2.in' }
  return new Promise((ok) => {
    gsap.to(els, { ...vars, onComplete: () => ok() })
  })
}

/**
 * Reacomoda las tarjetas de `contenedor` alrededor de `cambio` (filtrar, sumar, completar):
 * las que quedan se corren con GSAP Flip y las que aparecen entran girando (en el celu, con
 * fundido y escala; con movimiento suave, solo fundido).
 */
export async function reacomodar(contenedor: Element, cambio: () => void | Promise<void>, celu = false): Promise<void> {
  const antes = new Set(contenedor.children)
  if (isSoft()) {
    await cambio()
    await nextTick()
    const nuevas = [...contenedor.children].filter((c) => !antes.has(c))
    if (nuevas.length) gsap.fromTo(nuevas, { opacity: 0 }, { opacity: 1, duration: FUNDIDO, clearProps: 'opacity' })
    return
  }
  const estado = Flip.getState([...antes])
  await cambio()
  await nextTick()
  Flip.from(estado, {
    targets: [...contenedor.children],
    scale: true,
    duration: celu ? 0.4 : 0.6,
    ease: celu ? 'power2.out' : 'back.out(1.3)',
    stagger: celu ? 0.02 : 0.03,
    onEnter: (els) =>
      celu
        ? gsap.fromTo(els, { opacity: 0, scale: 0.9 }, { opacity: 1, scale: 1, duration: 0.3, ease: 'power2.out', clearProps: 'transform,opacity' })
        : gsap.fromTo(els, { opacity: 0, scale: 0.2, rotation: -60 }, { opacity: 1, scale: 1, rotation: 0, duration: 0.5, ease: 'back.out(1.6)', clearProps: 'transform,opacity' }),
  })
}

/** El destino sirve para volar solo si se ve: con caja, y dentro de la pantalla. */
export function destinoVisible(el: Element | null): el is Element {
  if (!el) return false
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.height > 0 && r.bottom > 0 && r.right > 0 && r.top < window.innerHeight && r.left < window.innerWidth
}

/** Un latido de la marca NOTA cuando no hay adónde volar. */
export function pulsarMarca(marca: Element | null): void {
  if (!marca) return
  if (isSoft()) {
    gsap.fromTo(marca, { opacity: 0 }, { opacity: 1, duration: FUNDIDO, clearProps: 'opacity' })
    return
  }
  gsap.fromTo(marca, { scale: 1.5 }, { scale: 1, duration: 0.5, ease: 'back.out(2)', clearProps: 'transform' })
}

/**
 * Escena 2: el texto se despega del mensaje, se pliega en celda y vuela hacia la pestaña Notas.
 * Sin destino visible, solo late la marca. Con movimiento suave, un fundido.
 */
export function guardarEnNotas(origen: Element, destino: Element | null, marca?: Element | null): Promise<void> {
  if (!destinoVisible(destino)) {
    pulsarMarca(marca ?? null)
    return Promise.resolve()
  }
  if (isSoft()) {
    return new Promise((ok) => {
      gsap.fromTo(destino, { opacity: 0.4 }, { opacity: 1, duration: FUNDIDO, clearProps: 'opacity', onComplete: () => ok() })
    })
  }
  const r = origen.getBoundingClientRect()
  const d = destino.getBoundingClientRect()
  const alto = Math.min(r.height, TOPE_VUELO)
  const clon = origen.cloneNode(true) as HTMLElement
  clon.classList.add('nota-vuelo', 'nota-vuelo-tarjeta')
  clon.setAttribute('aria-hidden', 'true')
  clon.setAttribute('inert', '')
  const recortado = r.height > TOPE_VUELO
  Object.assign(clon.style, {
    position: 'fixed',
    left: `${r.left}px`,
    top: `${r.top}px`,
    width: `${r.width}px`,
    height: `${alto}px`,
    overflow: 'hidden',
    margin: '0',
    zIndex: '60',
    pointerEvents: 'none',
    boxSizing: 'border-box',
    padding: '10px 12px',
    borderRadius: '12px',
    background: 'var(--surface-2)',
    boxShadow: '0 18px 40px rgba(0,0,0,.35), inset 0 0 0 1.5px var(--miel)',
  })
  if (recortado) {
    const velo = document.createElement('i')
    velo.className = 'nota-vuelo-fade'
    Object.assign(velo.style, {
      position: 'absolute',
      left: '0',
      right: '0',
      bottom: '0',
      height: '36px',
      pointerEvents: 'none',
      background: 'linear-gradient(to bottom, transparent, var(--surface-2))',
    })
    clon.append(velo)
  }
  document.body.append(clon)
  const dx = d.left + d.width / 2 - (r.left + r.width / 2)
  const dy = d.top + d.height / 2 - (r.top + alto / 2)
  return new Promise((ok) => {
    const fin = () => {
      clon.remove()
      pulsarMarca(marca ?? null)
      ok()
    }
    try {
      gsap
        .timeline({ onComplete: fin })
        .fromTo(clon, { clipPath: RECT }, { clipPath: HEX, duration: 0.35, ease: 'power2.inOut' }, 0)
        .to(clon, { x: dx, y: dy, scale: 0.12, rotation: 24, duration: 0.7, ease: 'power2.in' }, 0.1)
        .to(clon, { opacity: 0, duration: 0.1 })
        .to(destino, { scale: 1.18, duration: 0.12, yoyo: true, repeat: 1 }, '<')
    } catch {
      clon.remove()
      ok()
    }
  })
}

export type ResultadoSalto = 'esperar' | 'saltado' | 'ausente'

/**
 * Decide qué hacer con un pedido de salto: espera hasta que la sesión abierta sea la del pedido,
 * haya cargado y tenga mensajes dibujados; recién entonces intenta saltar.
 */
export function resolverSalto(
  scroller: Element | null,
  salto: { sid: string; ts: string },
  sidAbierta: string | null,
  cargado: boolean,
): ResultadoSalto {
  if (!scroller || !cargado || salto.sid !== sidAbierta) return 'esperar'
  if (!scroller.getClientRects().length) return 'esperar'
  if (!scroller.querySelector('[data-ts], .msg')) return 'esperar'
  return saltarAMensaje(scroller, salto.ts) ? 'saltado' : 'ausente'
}

/** Lleva el scroll al mensaje con ese `ts` y lo resalta 1,5 s. Sin coincidencia no hace nada. */
export function saltarAMensaje(scroller: Element, ts: string): boolean {
  if (!ts) return false
  const el = [...scroller.querySelectorAll<HTMLElement>('[data-ts]')].find((e) => e.dataset.ts === ts)
  if (!el) return false
  el.scrollIntoView({ block: 'center', behavior: isSoft() ? 'auto' : 'smooth' })
  el.classList.add('resaltado')
  setTimeout(() => el.classList.remove('resaltado'), 1500)
  return true
}

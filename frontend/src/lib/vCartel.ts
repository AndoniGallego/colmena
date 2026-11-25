import type { Directive } from 'vue'
import { actualizarCartel, mostrarCartel, ocultarCartel } from '../state/cartel'
import type { Cartel } from './accionesBarra'

type Estado = { valor: Cartel; tocado: boolean; off: () => void }
const estados = new WeakMap<HTMLElement, Estado>()

const punteroFino = () => !!window.matchMedia?.('(hover: hover) and (pointer: fine)').matches

/**
 * Cartel rápido: nombre + una línea de para qué sirve.
 * Hover (solo puntero fino) con demora corta, teclado enseguida, Esc o salir lo cierra.
 * La descripción queda como aria-description; el botón no lleva title.
 */
export const vCartel: Directive<HTMLElement, Cartel> & { getSSRProps: (b: { value: Cartel }) => Record<string, string> } = {
  mounted(el, { value }) {
    const st: Estado = { valor: value, tocado: false, off: () => {} }
    estados.set(el, st)
    const on = <K extends keyof HTMLElementEventMap>(t: K, f: (e: HTMLElementEventMap[K]) => void) => {
      el.addEventListener(t, f)
      const prev = st.off
      st.off = () => {
        prev()
        el.removeEventListener(t, f)
      }
    }
    on('pointerenter', (e) => {
      if (e.pointerType === 'touch' || !punteroFino()) return
      mostrarCartel(el, st.valor.nombre, st.valor.desc, false)
    })
    on('pointerleave', () => ocultarCartel(el))
    on('pointerdown', () => {
      st.tocado = true
      ocultarCartel(el)
    })
    on('focus', () => {
      if (!st.tocado) mostrarCartel(el, st.valor.nombre, st.valor.desc, true)
    })
    on('blur', () => {
      st.tocado = false
      ocultarCartel(el)
    })
    on('keydown', (e) => {
      if (e.key === 'Escape') ocultarCartel(el)
    })
    el.setAttribute('aria-description', value.desc)
  },
  updated(el, { value }) {
    const st = estados.get(el)
    if (!st) return
    st.valor = value
    el.setAttribute('aria-description', value.desc)
    actualizarCartel(el, value.nombre, value.desc)
  },
  unmounted(el) {
    ocultarCartel(el)
    estados.get(el)?.off()
    estados.delete(el)
  },
  getSSRProps: ({ value }: { value: Cartel }) => ({ 'aria-description': value.desc }),
}

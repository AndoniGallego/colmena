import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'
import { resolverSalto } from '../lib/notasMovimiento'
import { saltoMensaje } from '../state/notas'

/**
 * Atiende el pedido de saltar a un mensaje (desde una nota): espera a que la sesión pedida esté
 * abierta, cargada, dibujada y visible; salta, o va al final si el mensaje no está, y recién ahí
 * limpia el pedido. Si el chat se cierra, descarta un pedido que quedó colgado.
 */
export function useSaltoMensaje(o: {
  scroller: Ref<HTMLElement | null>
  mensajes: Ref<number>
  sid: Ref<string | null>
  cargado: Ref<boolean>
  verCambios: Ref<boolean>
  stick: Ref<boolean>
  toBottom: () => void
}): void {
  let ro: ResizeObserver | null = null
  const soltar = () => {
    ro?.disconnect()
    ro = null
  }

  async function intentar() {
    const salto = saltoMensaje.value
    if (!salto || o.verCambios.value) return
    await nextTick()
    if (saltoMensaje.value !== salto) return
    const r = resolverSalto(o.scroller.value, salto, o.sid.value, o.cargado.value)
    if (r === 'esperar') {
      // Oculto por una transición o un panel: reintenta cuando el scroller tome tamaño.
      if (!ro && o.scroller.value && typeof ResizeObserver !== 'undefined') {
        ro = new ResizeObserver(() => void intentar())
        ro.observe(o.scroller.value)
      }
      return
    }
    soltar()
    if (r === 'saltado') o.stick.value = false
    else o.toBottom()
    saltoMensaje.value = null
  }

  watch(
    () => [saltoMensaje.value, o.cargado.value, o.sid.value, o.mensajes.value, o.verCambios.value] as const,
    () => void intentar(),
    { immediate: true, flush: 'post' },
  )
  watch(o.sid, (sid) => {
    if (sid === null) {
      soltar()
      saltoMensaje.value = null
    }
  })
  onBeforeUnmount(soltar)
}

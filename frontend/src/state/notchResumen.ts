import { computed, ref, watch, type Ref } from 'vue'
import { debeRetenerResumen, RETENER_RESUMEN_MS, type Resumen } from '../lib/notchCeldas'
import { modo, resumen } from './notch'
import { avisoActual } from './notchAvisos'

function copiarResumen(r: Resumen): Resumen {
  return { teToca: r.teToca, trabajando: r.trabajando, termino: r.termino }
}

export function crearResumenVisible(
  fuente: Ref<Resumen>,
  hayAviso: Ref<boolean>,
  ms = RETENER_RESUMEN_MS,
  destino?: Ref<Resumen>,
): { visible: Ref<Resumen>; detener: () => void } {
  const visible = destino ?? ref(copiarResumen(fuente.value))
  if (!destino) visible.value = copiarResumen(fuente.value)

  let timer: ReturnType<typeof setTimeout> | undefined

  function cancelarTimer() {
    if (timer !== undefined) {
      clearTimeout(timer)
      timer = undefined
    }
  }

  function aplicarFuente() {
    cancelarTimer()
    visible.value = copiarResumen(fuente.value)
  }

  function programarAplicar() {
    if (timer !== undefined) return
    timer = setTimeout(aplicarFuente, ms)
  }

  const stopFuente = watch(fuente, (nuevo) => {
    if (debeRetenerResumen(visible.value, nuevo)) {
      programarAplicar()
    } else {
      cancelarTimer()
      visible.value = copiarResumen(nuevo)
    }
  })

  const stopAviso = watch(hayAviso, (hay) => {
    if (hay) aplicarFuente()
  })

  function detener() {
    cancelarTimer()
    stopFuente()
    stopAviso()
  }

  return { visible, detener }
}

export const resumenVisible = ref<Resumen>({ teToca: 0, trabajando: 0, termino: 0 })

let detenerResumenVisible: (() => void) | undefined

export function _resetIniciarResumenVisible(): void {
  detenerResumenVisible?.()
  detenerResumenVisible = undefined
  resumenVisible.value = { teToca: 0, trabajando: 0, termino: 0 }
}

export function iniciarResumenVisible(): void {
  if (detenerResumenVisible) return
  resumenVisible.value = copiarResumen(resumen.value)
  const hayAviso = computed(() => modo.value === 'aviso' && !!avisoActual.value)
  const { detener } = crearResumenVisible(resumen, hayAviso, RETENER_RESUMEN_MS, resumenVisible)
  detenerResumenVisible = detener
}

import { nextTick, onBeforeUnmount, ref, type Ref } from 'vue'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { sacudir } from './errorEnLugar'

export function useConfirmacionBoton(duracion = 1200) {
  const hecho = ref(false)
  const error = ref('')
  const path = ref<SVGPathElement | null>(null)
  const { run } = useGsap()
  let timer: ReturnType<typeof setTimeout> | undefined

  async function pulsarHecho(pathRef?: Ref<SVGPathElement | null>) {
    hecho.value = true
    await nextTick()
    const p = pathRef?.value ?? path.value
    if (p && !isSoft()) run(() => gsap.fromTo(p, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.4, ease: 'power2.out' }))
    clearTimeout(timer)
    timer = setTimeout(() => (hecho.value = false), duracion)
  }

  async function conConfirmacion(fn: () => Promise<boolean>) {
    error.value = ''
    if (await fn()) {
      haptic(8)
      await pulsarHecho()
      return true
    }
    return false
  }

  function fallo(texto: string, el?: HTMLElement | null) {
    error.value = texto
    if (el) sacudir(el, run)
  }

  onBeforeUnmount(() => clearTimeout(timer))
  return { hecho, error, path, conConfirmacion, fallo, pulsarHecho }
}

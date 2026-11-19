import { ref } from 'vue'
import { gsap, isSoft, useGsap } from '../motion'

export function sacudir(el: Element | null | undefined, run: (fn: () => void) => void) {
  if (!el || isSoft()) return
  run(() => {
    gsap.fromTo(
      el,
      { x: 0 },
      {
        x: 0,
        duration: 0.45,
        ease: 'elastic.out(1, 0.55)',
        keyframes: [{ x: -9 }, { x: 8 }, { x: -5 }, { x: 3 }, { x: 0 }],
      },
    )
  })
}

export function useErrorEnLugar() {
  const error = ref('')
  const target = ref<HTMLElement | null>(null)
  const { run } = useGsap()

  function mostrar(msg: string, el?: HTMLElement | null) {
    error.value = msg
    sacudir(el ?? target.value, run)
  }

  function limpiar() {
    error.value = ''
  }

  return { error, target, mostrar, limpiar }
}

import { onBeforeUnmount, onMounted, ref } from 'vue'

const KEYBOARD_MIN = 120

// iOS no achica la página al abrir el teclado: lo tapa. Se mide con visualViewport y la app se ajusta a lo visible.
export function useKeyboard() {
  const open = ref(false)
  const height = ref<number | null>(null)
  /** iOS puede correr la vista sin scrollear la página (offsetTop): lo fijo se ubica con esto. */
  const top = ref(0)
  const vv = typeof window !== 'undefined' ? window.visualViewport : null

  const sync = () => {
    if (!vv) return
    const isOpen = window.innerHeight - vv.height > KEYBOARD_MIN
    open.value = isOpen
    height.value = isOpen ? Math.round(vv.height) : null
    top.value = isOpen ? Math.round(vv.offsetTop) : 0
    if (isOpen && (window.scrollY || vv.offsetTop)) window.scrollTo(0, 0)
    if (isOpen) {
      const el = document.activeElement as HTMLElement | null
      requestAnimationFrame(() => el?.scrollIntoView?.({ block: 'nearest' }))
    }
  }

  onMounted(() => {
    vv?.addEventListener('resize', sync)
    vv?.addEventListener('scroll', sync)
  })
  onBeforeUnmount(() => {
    vv?.removeEventListener('resize', sync)
    vv?.removeEventListener('scroll', sync)
  })
  return { open, height, top }
}

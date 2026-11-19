import { ref } from 'vue'
import { loadTheme, saveTheme, type Theme } from './storage'
import { isSoft } from '../motion'

export const theme = ref<Theme>(loadTheme())

/** Cambia el tema con el barrido circular que nace en `from` (o en el centro). */
export function setTheme(next: Theme, from?: HTMLElement | null) {
  if (next === theme.value) return
  const r = from?.getBoundingClientRect()
  const x = r ? r.left + r.width / 2 : innerWidth / 2
  const y = r ? r.top + r.height / 2 : innerHeight / 2
  const rs = document.documentElement.style
  rs.setProperty('--vt-x', `${x}px`)
  rs.setProperty('--vt-y', `${y}px`)
  rs.setProperty('--vt-r', `${Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y)) + 8}px`)
  theme.value = next
  const apply = () => {
    document.documentElement.dataset.theme = next
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', next === 'dark' ? '#0c0e0d' : '#f1efe7')
  }
  const doc = document as Document & { startViewTransition?: (cb: () => void) => unknown }
  if (doc.startViewTransition && !isSoft()) doc.startViewTransition(apply)
  else apply()
  saveTheme(next)
}

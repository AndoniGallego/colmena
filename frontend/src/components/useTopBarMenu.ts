import { ref } from 'vue'

/**
 * Menú "más" (compact) y popover de salida (escritorio): cierre con Esc y clic fuera.
 */
export function useTopBarMenu(revokeAllSessions: () => Promise<boolean>) {
  const menuOpen = ref(false)
  const menuConfirming = ref(false)
  const revoking = ref(false)
  const menuEl = ref<HTMLElement | null>(null)
  const menuPop = ref<HTMLElement | null>(null)
  const menuPos = ref({ top: 0, right: 0 })

  const salirPopOpen = ref(false)
  const salirBtnRef = ref<HTMLElement | null>(null)
  const salirPopRef = ref<HTMLElement | null>(null)
  const salirPos = ref({ top: 0, right: 0 })

  function closeMenu() {
    menuOpen.value = false
    menuConfirming.value = false
  }

  function closeSalirPopover() {
    salirPopOpen.value = false
  }

  function toggleMenu() {
    if (menuOpen.value) return closeMenu()
    const r = menuEl.value?.getBoundingClientRect()
    if (r) menuPos.value = { top: r.bottom + 8, right: Math.max(8, window.innerWidth - r.right) }
    menuOpen.value = true
  }

  function toggleSalirPopover() {
    if (salirPopOpen.value) {
      closeSalirPopover()
      return
    }
    const r = salirBtnRef.value?.getBoundingClientRect()
    if (r) salirPos.value = { top: r.bottom + 8, right: Math.max(8, window.innerWidth - r.right) }
    salirPopOpen.value = true
  }

  function onDoc(e: Event) {
    const t = e.target as Node
    if (menuOpen.value && menuEl.value && !menuEl.value.contains(t) && !menuPop.value?.contains(t)) closeMenu()
    if (salirPopOpen.value && salirBtnRef.value && !salirBtnRef.value.contains(t) && !salirPopRef.value?.contains(t)) closeSalirPopover()
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      closeMenu()
      closeSalirPopover()
    }
  }

  async function revoke() {
    revoking.value = true
    if (await revokeAllSessions()) {
      closeSalirPopover()
      closeMenu()
    } else {
      revoking.value = false
    }
  }

  function closeAllOverlays() {
    closeMenu()
    closeSalirPopover()
  }

  return {
    menuOpen,
    menuConfirming,
    revoking,
    menuEl,
    menuPop,
    menuPos,
    salirPopOpen,
    salirBtnRef,
    salirPopRef,
    salirPos,
    toggleMenu,
    closeMenu,
    toggleSalirPopover,
    closeSalirPopover,
    onDoc,
    onKey,
    revoke,
    closeAllOverlays,
  }
}

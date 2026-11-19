import { ref } from 'vue'
import type { LogoVariant } from '../lib/colmena'
import { loadLogo, saveLogo } from '../lib/storage'

/** Variante de logo elegida en Ajustes; se aplica en toda la app. */
export const logoVariant = ref<LogoVariant>(loadLogo())

export function setLogo(v: LogoVariant) {
  if (v === logoVariant.value) return
  logoVariant.value = v
  saveLogo(v)
}

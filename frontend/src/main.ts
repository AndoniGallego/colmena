import '@fontsource-variable/bricolage-grotesque/opsz.css'
import '@fontsource-variable/instrument-sans/wght.css'
import '@fontsource-variable/instrument-sans/wght-italic.css'
import '@fontsource-variable/jetbrains-mono/wght.css'
import { createApp } from 'vue'
import './styles/base.css'
import './styles/ui.css'
import { createHttpApi } from './api/http'
import type { Api } from './api/types'
import { boot, init, onUnauthorized } from './state/app'
import { loadTheme } from './lib/storage'
import { aplicarBarraScroll } from './lib/scrollbar'
import { instalarCopiaCodigo } from './lib/codeCopy'
import { esRutaNotch } from './lib/notchPuente'
import { precargarChat } from './lib/precarga'
import { correrGancho, piezas } from './piezas'
import { bloquearRedEnDemo, DEMO } from './lib/demoActual'
import { registrarServiceWorker, usarMock } from './lib/modoDemo'

if (import.meta.env.DEV) void import('./lib/vitalsDev').then((m) => m.medirVitalsDev())

document.documentElement.dataset.theme = loadTheme()
instalarCopiaCodigo(document)

const notch = esRutaNotch(location.pathname)

let api: Api = createHttpApi(onUnauthorized, () => piezas().flatMap((p) => (p.avisos ? [p.avisos.kind] : [])))
if (DEMO) bloquearRedEnDemo()
if (usarMock({ demo: DEMO, dev: import.meta.env.DEV, search: location.search })) {
  for (const p of piezas()) await correrGancho(p, 'mock')
  const { createMockApi } = await import('./mock/mockApi')
  api = createMockApi(onUnauthorized)
  const { createMockMrs } = await import('./mock/mockMrs')
  const { setMrsApi } = await import('./state/mrs')
  setMrsApi(createMockMrs())
  const { mockCambios } = await import('./mock/mockCambios')
  const { setCambiosApi } = await import('./state/cambios')
  setCambiosApi(mockCambios)
}

init(api, notch ? { presencia: false, ligero: true } : {})

if (notch) {
  const { default: NotchApp } = await import('./components/notch/NotchApp.vue')
  createApp(NotchApp).mount('#app')
} else {
  const { default: App } = await import('./App.vue')
  createApp(App).mount('#app')
  aplicarBarraScroll(document)
  precargarChat()
}

void boot()

if (registrarServiceWorker({ demo: DEMO, prod: import.meta.env.PROD, notch, tieneSW: 'serviceWorker' in navigator, seguro: window.isSecureContext })) {
  window.addEventListener('load', () => void navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`))
}

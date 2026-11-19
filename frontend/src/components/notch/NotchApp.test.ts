import { computed, createSSRApp, h, ref } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { AvisoNotch } from '../../lib/notchAvisos'
import { BRILLO_AVISO_KIND } from '../../lib/notchAvisos'

vi.hoisted(() => {
  vi.stubGlobal('window', {
    matchMedia: () => ({ matches: false, addEventListener() {} }),
    addEventListener() {},
    removeEventListener() {},
    screen: { availWidth: 800, availHeight: 600 },
  })
  vi.stubGlobal('ResizeObserver', class {
    observe() {}
    disconnect() {}
  })
})

const modo = ref<'cerrado' | 'panel' | 'aviso'>('aviso')
const avisoActual = ref<AvisoNotch | null>({
  id: 1,
  kind: 'done',
  titulo: 'Colmena terminó',
  cuerpo: 'Listo',
  session_id: 's1',
})
const auth = ref<'checking' | 'login' | 'ready' | 'forbidden' | 'offline'>('ready')

vi.mock('../../motion', async () => {
  const { ref: r } = await import('vue')
  return {
    gsap: {
      set() {},
      to() {},
      fromTo() {},
      from() {},
      killTweensOf() {},
      timeline: () => ({ to() { return this }, fromTo() { return this }, kill() {} }),
      delayedCall() {},
      utils: { random: () => 1 },
    },
    isSoft: () => true,
    soft: r(true),
    brandHop: r(0),
    useGsap: () => ({ run: (fn: () => void) => fn() }),
  }
})

vi.mock('../logo/LogoPanal.vue', () => ({
  default: { name: 'LogoPanal', props: ['size', 'cells', 'live', 'loader', 'intro'], template: '<span />' },
}))

vi.mock('./NotchAviso.vue', () => ({
  default: { name: 'NotchAviso', props: ['aviso', 'sesion', 'now'], template: '<div class="aviso-stub" />' },
}))

vi.mock('./NotchPanel.vue', () => ({
  default: { name: 'NotchPanel', props: ['grupos', 'now'], template: '<div class="panel-stub" />' },
}))

vi.mock('./NotchLogin.vue', () => ({
  default: { name: 'NotchLogin', template: '<div class="login-stub" />' },
}))

vi.mock('../../state/app', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../state/app')>()
  return { ...actual, auth }
})

vi.mock('../../state/notch', () => ({
  modo,
  celdas: computed(() => []),
  enVivo: ref(false),
  grupos: computed(() => []),
  sesiones: computed(() => []),
  alternarPanel: vi.fn(),
  cerrarPanel: vi.fn(),
  abrirSesion: vi.fn(),
  abrirColmena: vi.fn(),
  setPuente: vi.fn(),
}))

vi.mock('../../state/notchAvisos', () => ({
  avisoActual,
  cerrarAviso: vi.fn(),
  iniciarAvisosNotch: vi.fn(),
}))

vi.mock('../../state/notchResumen', () => ({
  resumenVisible: ref({ teToca: 0, trabajando: 0, termino: 0 }),
  iniciarResumenVisible: vi.fn(),
}))

vi.mock('../../lib/notchPuente', () => ({
  crearPuente: () => ({
    enPrograma: false,
    tamano() {},
    forma() {},
    arrastrar() {},
    abrirColmena() {},
    aviso() {},
  }),
}))

describe('NotchApp brillo en pastilla', () => {
  it('con aviso done la pastilla tiene brillo; sin aviso no', async () => {
    modo.value = 'aviso'
    avisoActual.value = {
      id: 1,
      kind: 'done',
      titulo: 'Colmena terminó',
      cuerpo: 'Listo',
      session_id: 's1',
    }
    auth.value = 'ready'

    const { default: NotchApp } = await import('./NotchApp.vue')
    const htmlConAviso = await renderToString(createSSRApp({ render: () => h(NotchApp) }))
    expect(htmlConAviso).toContain('pill-brillo')
    expect(htmlConAviso).toContain(BRILLO_AVISO_KIND.done)

    avisoActual.value = null
    modo.value = 'panel'
    const htmlSinAviso = await renderToString(createSSRApp({ render: () => h(NotchApp) }))
    expect(htmlSinAviso).not.toContain('pill-brillo')
  })
})

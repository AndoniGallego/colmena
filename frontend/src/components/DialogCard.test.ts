import { createSSRApp, h, reactive } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'
import type { DialogView } from '../api/types'

const dlg = reactive({
  sessionId: 's1' as string | null,
  view: null as DialogView | null,
  loading: false,
  loadError: null as string | null,
  phase: 'idle' as const,
  notice: null as string | null,
  noticeKind: null,
  pin: { open: false, error: null, lockedUntil: null, huella: null, regla: null, choice: null, pedidoId: null },
  sent: [] as string[],
})

vi.mock('../motion', () => ({
  gsap: {},
  isSoft: () => true,
  useGsap: () => ({ run: (fn: () => void) => fn() }),
}))
vi.mock('../state/app', () => ({ boardState: { value: { board: null } } }))
vi.mock('../state/session', () => ({ dialogoLink: { value: false } }))
vi.mock('../state/dialogo', () => ({
  dlg,
  loadDialog: vi.fn(),
  resetDialog: vi.fn(),
  answerPermiso: vi.fn(),
  answerPregunta: vi.fn(),
  askPin: vi.fn(),
  decidirPedido: vi.fn(),
}))
vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./PedidoCard.vue', () => ({ default: { template: '<div />' } }))

const { default: DialogCard } = await import('./DialogCard.vue')

const desconocido: DialogView = { tipo: 'desconocido', paneId: 'w1:p1', pantalla: 'algo raro' }

async function renderCard(props: { sessionId?: string; status?: string; tabId?: string; vivo?: boolean }) {
  dlg.view = desconocido
  dlg.sessionId = props.sessionId ?? 's1'
  return renderToString(
    createSSRApp({
      render: () =>
        h(DialogCard, {
          sessionId: props.sessionId ?? 's1',
          status: props.status ?? 'blocked',
          tabId: props.tabId ?? 'tab-1',
          vivo: props.vivo,
        }),
    }),
  )
}

describe('DialogCard desconocido', () => {
  it('con vivo=true muestra Abrir terminal y no Enfocar en la PC', async () => {
    const html = await renderCard({ vivo: true })
    expect(html).toContain('Abrir terminal')
    expect(html).not.toContain('Enfocar en la PC')
    expect(html).toContain('Abrí la terminal para verlo y responderlo.')
  })

  it('con vivo=false no muestra Enfocar ni Abrir terminal', async () => {
    const html = await renderCard({ vivo: false })
    expect(html).not.toContain('Enfocar')
    expect(html).not.toContain('Abrir terminal')
    expect(html).toContain('Respondelo en la terminal.')
  })
})

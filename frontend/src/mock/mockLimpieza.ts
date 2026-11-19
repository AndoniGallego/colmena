import { ApiError, type Api, type ClosePane, type ClosePreview, type LimpiezaItem } from '../api/types'

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

const ses = (id: string, titulo: string, pendiente: string) => ({ session_id: id, titulo, ultima: new Date(Date.now() - 9 * 86_400_000).toISOString(), pendiente })

const base = (): LimpiezaItem[] => [
  { tipo: 'tab', target_id: 'm1:t1', workspace: 'Imagenes CDN', label: 'CloudFront', razones: [{ tipo: 'quieto', dias: 9 }], sesiones: [ses('s-m1', 'Distribución de imágenes', 'Quedó listo el bucket; falta decidir las invalidaciones por prefijo.')], terminales: 1, marcado: true, bloqueado: null },
  { tipo: 'tab', target_id: 'm1:t2', workspace: 'Imagenes CDN', label: 'Headers de cache', razones: [{ tipo: 'quieto', dias: 8 }, { tipo: 'mergeada', rama: 'feature/DEMO-88', base: 'origin/main' }], sesiones: [ses('s-m2', 'Headers de cache', '')], terminales: 1, marcado: true, bloqueado: null },
  { tipo: 'tab', target_id: 'm2:t1', workspace: 'Categorizador', label: 'Terminal vieja', razones: [{ tipo: 'sin_claude', dias: 12 }], sesiones: [], terminales: 1, marcado: true, bloqueado: null },
  { tipo: 'workspace', target_id: 'm3', workspace: 'Experimento SSO', label: 'Experimento SSO', razones: [{ tipo: 'quieto', dias: 14 }], sesiones: [ses('s-m3', 'Prueba de claims', 'Sin pendientes.')], terminales: 2, marcado: false, bloqueado: null },
  { tipo: 'tab', target_id: 'm4:t1', workspace: 'Categorizador', label: 'Backfill', razones: [{ tipo: 'quieto', dias: 10 }], sesiones: [ses('s-m4', 'Backfill web', '')], terminales: 1, marcado: false, bloqueado: 'corriendo' },
  { tipo: 'tab', target_id: 'm5:t1', workspace: 'Viajecito', label: 'Mapa', razones: [{ tipo: 'quieto', dias: 8 }], sesiones: [ses('s-m5', 'Mapa de lugares', 'Te dejé una pregunta sobre los íconos.')], terminales: 1, marcado: false, bloqueado: 'sin_leer' },
]

/** Mock de limpieza: seis candidatas (una mergeada, una sin Claude, una con proceso, una sin leer, un workspace entero). */
export function createMockLimpieza(): Pick<Api, 'getLimpieza' | 'previewLimpieza' | 'ejecutarLimpieza'> {
  const cerradas = new Set<string>()
  const vivas = () => base().filter((i) => !cerradas.has(i.target_id))
  const panes = (i: LimpiezaItem): ClosePane[] => [
    { pane_id: `${i.target_id}:p1`, kind: i.sesiones.length ? 'claude' : null, status: i.sesiones.length ? 'idle' : null, titulo: i.sesiones[0]?.titulo ?? '', session_id: i.sesiones[0]?.session_id ?? null, cwd: '/home/usuario/proyectos/tienda-demo', proceso: null },
  ]
  const preview = (i: LimpiezaItem): ClosePreview => ({
    tipo: i.tipo,
    target_id: i.target_id,
    label: i.label,
    workspace_label: i.workspace,
    cierra_workspace: i.tipo === 'workspace',
    tab_count: 1,
    panes: panes(i),
    bloqueantes: [],
    huella: `mock-${i.target_id}`,
  })
  return {
    async getLimpieza(dias) {
      await sleep(350)
      const d = dias ?? 7
      return { dias: d, items: vivas().filter((i) => i.razones.some((r) => r.tipo === 'mergeada' || r.tipo === 'sin_claude' || r.dias >= d)), generado_at: new Date().toISOString(), git: 'ok' }
    },
    async previewLimpieza(items) {
      await sleep(500)
      return items.map((x) => {
        const i = base().find((b) => b.target_id === x.target_id)
        if (!i || cerradas.has(x.target_id)) return { ...x, preview: null, error: 'Ya no está', bloqueantes: [] }
        if (i.target_id === 'm3') return { ...x, preview: null, error: 'Cambió: volvió a tener actividad', bloqueantes: [] }
        return { ...x, preview: preview(i), error: '', bloqueantes: [] }
      })
    },
    async ejecutarLimpieza(body, h, signal) {
      if (new URLSearchParams(location.search).get('limpieza') === 'rota') throw new ApiError(500, 'Fallo simulado')
      let ok = 0
      for (const it of body.items) {
        if (signal.aborted) break
        await sleep(700)
        const i = base().find((b) => b.target_id === it.target_id)
        if (it.target_id === 'm2:t1' && !cerradas.has('fail-once')) {
          cerradas.add('fail-once')
          h.onItem({ target_id: it.target_id, ok: false, error: 'No pude cerrarlo: las terminales no respondieron', sesiones: [] })
          continue
        }
        cerradas.add(it.target_id)
        ok++
        h.onItem({ target_id: it.target_id, ok: true, error: '', sesiones: i?.sesiones.map((s) => ({ session_id: s.session_id, cwd: '/home/usuario/proyectos/tienda-demo', titulo: s.titulo })) ?? [] })
      }
      h.onFin({ cerrados: ok, salteados: body.items.length - ok })
    },
  }
}

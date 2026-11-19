import { computed, reactive, watch } from 'vue'
import { ApiError, type CloseSession, type Guardado, type GuardadoAccion, type LimpiezaItem, type LimpiezaPreviewItem } from '../api/types'
import { clampDias, itemKey, marcasIniciales, motivoRevision, selectable } from '../lib/limpieza'
import { loadLimpiezaDias, saveLimpiezaDias } from '../lib/storage'
import { newId } from '../lib/reply'
import { haptic } from '../motion'
import { accionGuardado, boardState, ejecutarLimpieza, getLimpieza, previewLimpieza } from './app'

export type LimpiezaPaso = 'elegir' | 'revisar' | 'cerrando' | 'fin'

export interface Resultado {
  ok: boolean
  error: string
  sesiones: CloseSession[]
}

export const lm = reactive({
  items: [] as LimpiezaItem[],
  git: 'ok' as 'ok' | 'parcial' | 'sin_datos',
  dias: loadLimpiezaDias() ?? 0,
  /** el usuario tocó el stepper: ese valor manda sobre el default del server */
  propio: loadLimpiezaDias() !== null,
  loaded: false,
  recalculando: false,
  error: '',
  open: false,
  paso: 'elegir' as LimpiezaPaso,
  marcas: {} as Record<string, boolean>,
  revisando: false,
  previews: {} as Record<string, LimpiezaPreviewItem>,
  motivos: {} as Record<string, string>,
  resultados: {} as Record<string, Resultado>,
  aviso: '',
  /** el guardado en Engram que corre antes de cerrar (sección 16) */
  lote: null as Guardado | null,
  accionando: false,
  cerrados: 0,
  salteados: 0,
  /** sube cada vez que cambia el paso, para animar */
  tick: 0,
})

export const libres = computed(() => lm.items.filter(selectable))
export const hayCandidatas = computed(() => libres.value.length > 0)
export const marcadas = computed(() => lm.items.filter((i) => selectable(i) && lm.marcas[itemKey(i)]))
export const revisadas = computed(() => marcadas.value.filter((i) => !lm.motivos[itemKey(i)] && lm.previews[itemKey(i)]?.preview))
export const fallidas = computed(() => lm.items.filter((i) => lm.resultados[itemKey(i)] && !lm.resultados[itemKey(i)].ok))

let seq = 0
let revSeq = 0
let abort: AbortController | null = null

function mergeMarks(preseleccion?: string[] | null) {
  const fresh = marcasIniciales(lm.items, preseleccion)
  const next: Record<string, boolean> = {}
  for (const [k, v] of Object.entries(fresh)) next[k] = !preseleccion && k in lm.marcas ? lm.marcas[k] : v
  lm.marcas = next
}

export async function refreshLimpieza(preseleccion?: string[] | null): Promise<void> {
  const mine = ++seq
  try {
    const r = await getLimpieza(lm.propio ? lm.dias : null)
    if (mine !== seq) return
    if (lm.paso !== 'elegir') return
    lm.items = r.items
    lm.git = r.git
    if (!lm.propio) lm.dias = r.dias
    lm.loaded = true
    lm.error = ''
    mergeMarks(preseleccion)
  } catch (e) {
    if (mine !== seq) return
    lm.error = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  } finally {
    if (mine === seq) lm.recalculando = false
  }
}

let timer: ReturnType<typeof setTimeout> | undefined
let last = 0
const MIN_GAP = 30_000

/** El tablero se mueve seguido: se vuelve a preguntar como mucho cada 30 s (el server además cachea 60 s). */
export function scheduleLimpieza() {
  if (timer) return
  const wait = Math.max(1500, MIN_GAP - (Date.now() - last))
  timer = setTimeout(() => {
    timer = undefined
    last = Date.now()
    if (!lm.open) void refreshLimpieza()
  }, wait)
}

let started = false
export function initLimpieza() {
  if (started) return
  started = true
  last = Date.now()
  void refreshLimpieza()
  watch(
    () => boardState.value.board?.updated_at,
    () => scheduleLimpieza(),
  )
}

const bump = () => lm.tick++

export function abrirLimpieza(preseleccion?: string[] | null) {
  if (lm.open) return
  Object.assign(lm, { open: true, paso: 'elegir', previews: {}, motivos: {}, resultados: {}, aviso: '', lote: null, accionando: false, cerrados: 0, salteados: 0, revisando: false })
  if (lm.loaded) mergeMarks(preseleccion)
  void refreshLimpieza(preseleccion)
  bump()
}

export function cerrarHoja() {
  if (lm.paso === 'cerrando') return
  abort?.abort()
  const hubo = lm.paso === 'fin'
  lm.open = false
  lm.paso = 'elegir'
  lm.previews = {}
  lm.motivos = {}
  lm.resultados = {}
  lm.revisando = false
  if (hubo) void refreshLimpieza()
}

export function setDias(n: number) {
  const dias = clampDias(n)
  if (dias === lm.dias || lm.paso !== 'elegir') return
  lm.dias = dias
  lm.propio = true
  saveLimpiezaDias(dias)
  lm.recalculando = true
  void refreshLimpieza()
}

export function toggleMarca(key: string) {
  const item = lm.items.find((i) => itemKey(i) === key)
  if (!item || !selectable(item) || lm.paso !== 'elegir') return
  lm.marcas = { ...lm.marcas, [key]: !lm.marcas[key] }
}

export function volverAElegir() {
  if (lm.paso !== 'revisar') return
  revSeq++
  abort?.abort()
  lm.paso = 'elegir'
  lm.revisando = false
  bump()
}

export async function revisar(): Promise<void> {
  const items = marcadas.value
  if (!items.length || lm.paso === 'cerrando') return
  lm.paso = 'revisar'
  lm.revisando = true
  lm.previews = {}
  lm.motivos = {}
  bump()
  const mine = ++revSeq
  try {
    const out = await previewLimpieza(items.map((i) => ({ tipo: i.tipo, target_id: i.target_id })))
    if (mine !== revSeq || lm.paso !== 'revisar') return
    const previews: Record<string, LimpiezaPreviewItem> = {}
    const motivos: Record<string, string> = {}
    const marcas = { ...lm.marcas }
    for (const item of items) {
      const k = itemKey(item)
      const p = out.find((x) => itemKey(x) === k) ?? { tipo: item.tipo, target_id: item.target_id, preview: null, error: 'Cambió', bloqueantes: [] }
      previews[k] = p
      const motivo = motivoRevision(p)
      if (motivo) {
        motivos[k] = motivo
        marcas[k] = false
      }
    }
    lm.previews = previews
    lm.motivos = motivos
    lm.marcas = marcas
  } catch (e) {
    if (mine !== revSeq) return
    lm.paso = 'elegir'
    lm.aviso = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
    bump()
  } finally {
    if (mine === revSeq) lm.revisando = false
  }
}

export async function confirmar(sinGuardar = false): Promise<void> {
  const items = revisadas.value
  if (lm.paso !== 'revisar' || lm.revisando || !items.length) return
  const lote = newId()
  const body = {
    lote_id: lote,
    dias: lm.dias,
    ...(sinGuardar ? { sin_guardar: true } : {}),
    items: items.map((i) => ({ id: newId(), tipo: i.tipo, target_id: i.target_id, huella: lm.previews[itemKey(i)].preview!.huella })),
  }
  const byTarget = new Map(items.map((i) => [i.target_id, itemKey(i)]))
  lm.paso = 'cerrando'
  lm.resultados = {}
  lm.aviso = ''
  lm.lote = null
  bump()
  abort = new AbortController()
  const done = (id: string, r: Resultado) => {
    const k = byTarget.get(id)
    if (k) lm.resultados = { ...lm.resultados, [k]: r }
  }
  try {
    await ejecutarLimpieza(
      body,
      {
        onItem: (r) => {
          done(r.target_id, { ok: r.ok, error: r.error, sesiones: r.sesiones })
          if (r.ok) haptic(10)
        },
        onGuardando: (g) => (lm.lote = g),
        onFin: (f) => {
          lm.cerrados = f.cerrados
          lm.salteados = f.salteados
        },
      },
      abort.signal,
    )
  } catch (e) {
    const detail = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
    for (const i of items) if (!lm.resultados[itemKey(i)]) done(i.target_id, { ok: false, error: e instanceof ApiError ? detail : 'No pude confirmar si se cerró: revisá el tablero', sesiones: [] })
  }
  for (const i of items) if (!lm.resultados[itemKey(i)]) done(i.target_id, { ok: false, error: 'No pude confirmar si se cerró: revisá el tablero', sesiones: [] })
  const rs = Object.values(lm.resultados)
  lm.cerrados = rs.filter((r) => r.ok).length
  lm.salteados = rs.length - lm.cerrados
  lm.lote = null
  lm.paso = 'fin'
  bump()
}

/** "Cerrar igual" / "Esperar más" mientras las sesiones terminan de guardar. */
export async function accionLimpieza(accion: GuardadoAccion): Promise<void> {
  const g = lm.lote
  if (!g || lm.paso !== 'cerrando' || lm.accionando) return
  lm.accionando = true
  try {
    lm.lote = await accionGuardado(g.id, accion)
  } catch (e) {
    lm.aviso = e instanceof ApiError ? e.detail : 'Se cortó la conexión con el servidor'
  } finally {
    lm.accionando = false
  }
}

/** Las que quedaron abiertas vuelven a la revisión, con vista nueva y otra vez con "mantener apretado". */
export function reintentar(keys: string[]) {
  if (lm.paso !== 'fin') return
  const set = new Set(keys)
  const marcas: Record<string, boolean> = {}
  for (const i of lm.items) if (selectable(i)) marcas[itemKey(i)] = set.has(itemKey(i))
  lm.marcas = marcas
  lm.resultados = {}
  void revisar()
}

export const resultadoDe = (i: LimpiezaItem): Resultado | undefined => lm.resultados[itemKey(i)]


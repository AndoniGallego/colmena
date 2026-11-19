import { computed, reactive, ref, watch } from 'vue'
import {
  asignarCeldas,
  estadosCeldas,
  gruposPanel,
  resumenNotch,
  sesionesNotch,
} from '../lib/notchCeldas'
import type { ModoNotch } from '../lib/notchMovimiento'
import { emitir, escuchar, type Puente } from '../lib/notchPuente'
import { agentesTeToca, teTocaItems } from '../lib/teToca'
import { boardState } from './app'
import { pedidosAbiertos } from './permisos'
import { pedidosPestana } from './pedidosPestana'

export const modo = ref<ModoNotch>('cerrado')
export const asignacion = ref<(string | null)[]>([])
export const enviadas = reactive(new Map<string, number>())

const puenteStub: Puente = {
  enPrograma: false,
  tamano() {},
  forma() {},
  arrastrar() {},
  abrirColmena() {},
  aviso() {},
}
let bridge: Puente = puenteStub

export function setPuente(p: Puente) {
  bridge = p
}

export function puente() {
  return bridge
}

export const sesiones = computed(() => {
  const board = boardState.value.board
  const items = teTocaItems({
    agentes: agentesTeToca(board),
    pedidos: pedidosAbiertos,
    pedidosPestana: pedidosPestana.items,
    now: Date.now(),
  })
  return sesionesNotch({
    board,
    items,
    enviadas: new Set(enviadas.keys()),
  })
})

watch(
  sesiones,
  (s) => {
    asignacion.value = asignarCeldas(asignacion.value, s)
  },
  { immediate: true },
)

export const celdas = computed(() => estadosCeldas(asignacion.value, sesiones.value))
export const grupos = computed(() => gruposPanel(asignacion.value, sesiones.value))
export const resumen = computed(() => resumenNotch(sesiones.value))
export const enVivo = computed(() => boardState.value.connection === 'live')

export function alternarPanel() {
  if (modo.value === 'notas') {
    cerrarNotas()
    return
  }
  if (modo.value === 'aviso') {
    void import('./notchAvisos').then(({ limpiarColaAvisoVisible }) => limpiarColaAvisoVisible())
  }
  modo.value = modo.value === 'panel' ? 'cerrado' : 'panel'
}

export function cerrarPanel() {
  if (modo.value === 'panel') modo.value = 'cerrado'
}

/** Captura rápida de una nota (botón del panel o atajo global de Windows). */
export function abrirNotas() {
  modo.value = 'notas'
}

/** El atajo global de la app de Windows manda `notas-abrir`; al quedar escuchando avisa `notch-listo`. */
export function iniciarEscuchaNotas() {
  void escuchar('notas-abrir', abrirNotas).then((ok) => {
    if (ok) emitir('notch-listo')
  })
}

export function cerrarNotas() {
  if (modo.value === 'notas') modo.value = 'cerrado'
}

export function abrirSesion(sessionId: string) {
  bridge.abrirColmena(sessionId)
  if (modo.value === 'panel') cerrarPanel()
}

export function abrirColmena() {
  bridge.abrirColmena(null)
  if (modo.value === 'panel') cerrarPanel()
}

const ENVIO_TTL_MS = 60_000

function itemsTeToca() {
  const board = boardState.value.board
  return teTocaItems({
    agentes: agentesTeToca(board),
    pedidos: pedidosAbiertos,
    pedidosPestana: pedidosPestana.items,
    now: Date.now(),
  })
}

watch(sesiones, (list) => {
  void import('./notchRespuesta').then(({ activa, activar }) => {
    if (!boardState.value.board) return
    const now = Date.now()
    const items = itemsTeToca()
    for (const [sid, ts] of [...enviadas]) {
      if (now - ts >= ENVIO_TTL_MS) {
        enviadas.delete(sid)
        continue
      }
      const it = items.find((x) => x.sid === sid)
      if (!it || (it.motivo !== 'permiso' && it.motivo !== 'pregunta')) enviadas.delete(sid)
    }

    const teToca = list.filter((s) => s.estado === 'te-toca')
    const activaOk = activa.value && teToca.some((s) => s.session_id === activa.value)
    if (!activaOk) {
      const next = teToca[0]
      if (next) activar(next.session_id, next)
      else activa.value = null
    }
  })
})

const vistoActiva = ref<{ sid: string; estado: string; motivo: string | null; last: string | null } | null>(null)

watch(sesiones, (list) => {
  void import('./notchRespuesta').then(({ activa, recargar }) => {
    const sid = activa.value
    if (!sid) {
      vistoActiva.value = null
      return
    }
    const s = list.find((x) => x.session_id === sid)
    if (!s) return
    const snap = { sid, estado: s.estado, motivo: s.motivo, last: s.last_activity }
    const prev = vistoActiva.value
    vistoActiva.value = snap
    if (prev?.sid === sid && (prev.estado !== snap.estado || prev.motivo !== snap.motivo || prev.last !== snap.last)) {
      recargar(sid, s)
    }
  })
})

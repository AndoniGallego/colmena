import { ref } from 'vue'
import type { EstadoLector, LectorConectado } from '../lib/reunionPuente'
import { mostrar, MENSAJE_MOSTRAR } from '../lib/mostrarPuente'
import { emitir } from '../lib/notchPuente'

/** El panel muestra y el estado guarda como mucho estas líneas, las más nuevas arriba. */
export const LINEAS_VISIBLES = 30

type EstadoRespuesta = 'buscando' | 'en_cola' | 'lista' | 'error'

export interface LineaReunion {
  id: string
  texto: string
  tipo: 'pregunta' | 'requerimiento' | 'clave' | 'manual' | 'mostrar'
  respuesta?: { estado: EstadoRespuesta; texto: string; archivos: string[] }
  /** Id de la nota en que se anotó la línea. */
  nota?: string
  /** Ya se guardó en la memoria de trabajo. */
  memoria?: boolean
}

export interface EstadoReunionFront {
  reunion: string | null
  estado: 'inactiva' | 'escuchando' | 'pausada' | 'sin_pc' | 'llena' | 'terminando' | 'guardada'
  lector: EstadoLector
  /** Llegó al tope de detecciones automáticas. */
  tope: boolean
  /** El tope vale 0: no hay detección automática, solo a mano. */
  soloAMano: boolean
  detecciones: number
  topeDetecciones: number
  copiloto: 'abriendo' | 'listo' | 'sin_copiloto'
  /** Pasaron 2 minutos escuchando y no llegó nada de texto. */
  sinTexto: boolean
  /** El Copiloto está atendiendo una pregunta o un Mostrame. */
  ocupado: boolean
  /** Hay memoria de trabajo configurada: se puede guardar lo anotado. */
  memoriaTrabajo: boolean
  /** Subtítulos está acoplado: no se puede esconder y se ve al compartir pantalla. */
  cajitaAcoplada: boolean
  lineas: LineaReunion[]
  biblioteca: string | null
}

const ESTADOS = ['inactiva', 'escuchando', 'pausada', 'sin_pc', 'llena', 'terminando', 'guardada'] as const
const COPILOTO = ['abriendo', 'listo', 'sin_copiloto'] as const
const TIPOS = ['pregunta', 'requerimiento', 'clave', 'manual', 'mostrar'] as const
const RESPUESTAS: readonly string[] = ['buscando', 'en_cola', 'lista', 'error']

export function inicial(): EstadoReunionFront {
  return {
    reunion: null,
    estado: 'inactiva',
    lector: 'apagado',
    tope: false,
    soloAMano: false,
    detecciones: 0,
    topeDetecciones: 0,
    copiloto: 'abriendo',
    sinTexto: false,
    ocupado: false,
    memoriaTrabajo: false,
    cajitaAcoplada: false,
    lineas: [],
    biblioteca: null,
  }
}

const obj = (raw: unknown): Record<string, unknown> | null =>
  raw && typeof raw === 'object' && !Array.isArray(raw) ? (raw as Record<string, unknown>) : null
const enLista = <T extends string>(lista: readonly T[], v: unknown): v is T => typeof v === 'string' && (lista as readonly string[]).includes(v)
const cuenta = (v: unknown) => (typeof v === 'number' && Number.isFinite(v) && v >= 0 ? Math.floor(v) : 0)

function respuestaDe(raw: unknown): LineaReunion['respuesta'] {
  const r = obj(raw)
  if (!r || !RESPUESTAS.includes(r.estado as string)) return undefined
  return {
    estado: r.estado as EstadoRespuesta,
    texto: typeof r.texto === 'string' ? r.texto : '',
    archivos: Array.isArray(r.archivos) ? r.archivos.filter((a): a is string => typeof a === 'string') : [],
  }
}

function lineaDe(raw: unknown): LineaReunion | null {
  const l = obj(raw)
  if (!l || typeof l.id !== 'string' || !l.id || typeof l.texto !== 'string' || !enLista(TIPOS, l.tipo)) return null
  const respuesta = respuestaDe(l.respuesta)
  const nota = typeof l.nota === 'string' && l.nota ? l.nota : undefined
  return { id: l.id, texto: l.texto, tipo: l.tipo, ...(respuesta ? { respuesta } : {}), ...(nota ? { nota } : {}), ...(l.memoria === true ? { memoria: true } : {}) }
}

/** Campos del estado que vienen igual en el evento `reunion-estado` y en el snapshot. */
function camposEstado(d: Record<string, unknown>, base: EstadoReunionFront): EstadoReunionFront | null {
  if (!enLista(ESTADOS, d.estado)) return null
  return {
    ...base,
    estado: d.estado,
    tope: d.tope === true,
    soloAMano: d.solo_a_mano === true,
    detecciones: cuenta(d.detecciones),
    topeDetecciones: cuenta(d.tope_detecciones),
    copiloto: enLista(COPILOTO, d.copiloto) ? d.copiloto : base.copiloto,
    sinTexto: d.sin_texto === true,
    ocupado: d.ocupado === true,
    memoriaTrabajo: d.memoria_trabajo === true,
  }
}

/** Estado desde `GET /api/reunion/estado`; vacío o roto da el estado inactivo. */
export function desdeSnapshot(raw: unknown, lector: EstadoLector): EstadoReunionFront {
  const vacio = { ...inicial(), lector }
  const d = obj(raw)
  if (!d || typeof d.reunion !== 'string' || !d.reunion) return vacio
  const base = camposEstado(d, { ...vacio, reunion: d.reunion })
  if (!base) return vacio
  const lineas = (Array.isArray(d.lineas) ? d.lineas : [])
    .map(lineaDe)
    .filter((l): l is LineaReunion => l !== null)
    .reverse()
    .slice(0, LINEAS_VISIBLES)
  return { ...base, lineas }
}

/** Aplica un evento SSE `reunion-*`. Pura: si el evento no sirve devuelve el mismo objeto. */
export function aplicarEvento(e: EstadoReunionFront, evento: string, data: unknown): EstadoReunionFront {
  const d = obj(data)
  if (!d || typeof d.reunion !== 'string' || !d.reunion) return e

  if (evento === 'reunion-estado') {
    const enCurso = e.reunion !== null && e.estado !== 'guardada' && e.estado !== 'inactiva'
    if (enCurso && d.reunion !== e.reunion) return e
    const base = d.reunion === e.reunion ? e : { ...inicial(), lector: e.lector, cajitaAcoplada: e.cajitaAcoplada, reunion: d.reunion }
    return camposEstado(d, base) ?? e
  }

  if (d.reunion !== e.reunion) return e

  if (evento === 'reunion-linea') {
    const l = lineaDe({ id: d.id, texto: d.texto, tipo: d.tipo })
    if (!l || e.lineas.some((x) => x.id === l.id)) return e
    return { ...e, lineas: [l, ...e.lineas].slice(0, LINEAS_VISIBLES) }
  }

  if (evento === 'reunion-respuesta') {
    const respuesta = respuestaDe(d)
    if (!respuesta || typeof d.linea !== 'string') return e
    const i = e.lineas.findIndex((l) => l.id === d.linea)
    if (i < 0) return e
    const lineas = e.lineas.slice()
    lineas[i] = { ...lineas[i], respuesta }
    return { ...e, lineas }
  }

  if (evento === 'reunion-descartada') {
    if (typeof d.linea !== 'string' || !e.lineas.some((l) => l.id === d.linea)) return e
    return { ...e, lineas: e.lineas.filter((l) => l.id !== d.linea) }
  }

  if (evento === 'reunion-anotada') {
    if (typeof d.linea !== 'string' || typeof d.nota !== 'string' || !d.nota) return e
    const i = e.lineas.findIndex((l) => l.id === d.linea)
    if (i < 0) return e
    const lineas = e.lineas.slice()
    lineas[i] = { ...lineas[i], nota: d.nota }
    return { ...e, lineas }
  }

  if (evento === 'reunion-memoria') {
    const i = typeof d.linea === 'string' ? e.lineas.findIndex((l) => l.id === d.linea) : -1
    if (i < 0) return e
    const lineas = e.lineas.slice()
    lineas[i] = { ...lineas[i], memoria: true }
    return { ...e, lineas }
  }

  if (evento === 'reunion-guardada') {
    if (typeof d.biblioteca !== 'string' || !d.biblioteca) return e
    return { ...e, estado: 'guardada', biblioteca: d.biblioteca }
  }

  return e
}

// ---------- estado vivo y acciones ----------

export const reunion = ref<EstadoReunionFront>(inicial())
export interface RepoReunion {
  ruta: string
  nombre: string
}
export const repos = ref<RepoReunion[]>([])
export const rutaTodos = ref('')
/** Último error de una acción, en castellano; se limpia al probar de nuevo. */
export const errorReunion = ref<string | null>(null)

let device = ''
let lector: LectorConectado | null = null

export function fijarDevice(d: string) {
  device = d
}

export function fijarLector(l: LectorConectado | null) {
  lector = l
}

export const lectorConectado = () => lector !== null

/** Id con el que el lector puede mandar texto: la reunión lo recibe (en pausa o llena el back lo descarta). */
export function idParaTexto(): string | null {
  const r = reunion.value
  return r.reunion && (r.estado === 'escuchando' || r.estado === 'sin_pc') ? r.reunion : null
}

class ErrorHttp extends Error {
  constructor(readonly status: number) {
    super(String(status))
  }
}

async function pedir(metodo: 'GET' | 'POST', ruta: string, cuerpo?: unknown): Promise<unknown> {
  const res = await fetch(ruta, {
    method: metodo,
    credentials: 'same-origin',
    ...(cuerpo === undefined ? {} : { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(cuerpo) }),
  })
  if (!res.ok) throw new ErrorHttp(res.status)
  return res.json().catch(() => null)
}

export const postear = (ruta: string, cuerpo: unknown) => pedir('POST', ruta, cuerpo).then(() => undefined)

function invocar(cmd: string): Promise<unknown> {
  const invoke = window.__TAURI__?.core?.invoke
  if (typeof invoke !== 'function') return Promise.reject(new Error('sin app'))
  return invoke(cmd)
}

function mensajeDe(e: unknown, porDefecto: string): string {
  if (e instanceof ErrorHttp) {
    if (e.status === 409) return 'Ya hay una reunión en curso.'
    if (e.status === 422) return 'Esos repos ya no están disponibles. Elegí de nuevo.'
    if (e.status === 401 || e.status === 403) return 'Se venció la sesión. Entrá de nuevo.'
  }
  return porDefecto
}

/** Reunión viva (incluye `terminando`): mientras dure, el notch no se recarga solo. */
export function enCurso(e: EstadoReunionFront): boolean {
  return !!e.reunion && ['escuchando', 'pausada', 'sin_pc', 'llena', 'terminando'].includes(e.estado)
}

export function aplicarServidor(evento: string, data: unknown) {
  reunion.value = aplicarEvento(reunion.value, evento, data)
  // aplicarEvento es pura: el fin de la espera del Mostrame se limpia acá.
  const d = obj(data)
  if (evento === 'reunion-respuesta' && d && (d.estado === 'lista' || d.estado === 'error') && typeof d.linea === 'string') {
    if (mirando.value === d.linea) mirando.value = null
    // La respuesta pudo llegar antes del 202 del POST: se recuerda para cuando llegue.
    else if (mirando.value === 'capturando') terminadasEnVuelo.add(d.linea)
  }
  soltarMirando()
}

/** Id de la línea Mostrame en espera, o `'capturando'` entre el toque y el 202. */
export const mirando = ref<string | null>(null)
export const nudoPrendido = ref<boolean | null>(null)

let mirandoDe: string | null = null
const terminadasEnVuelo = new Set<string>()

/** Suelta `mirando` si la reunión cambió o ya no está en curso. */
function soltarMirando() {
  if (mirando.value === null) return
  if (!enCurso(reunion.value) || reunion.value.estado === 'terminando' || (mirandoDe !== null && reunion.value.reunion !== mirandoDe)) mirando.value = null
}

/** Con un snapshot del back: la línea en espera tiene que seguir buscando o en cola. */
function soltarMirandoSegunSnapshot() {
  soltarMirando()
  const id = mirando.value
  if (id === null || id === 'capturando') return
  const l = reunion.value.lineas.find((x) => x.id === id)
  if (!l || (l.respuesta?.estado !== 'buscando' && l.respuesta?.estado !== 'en_cola')) mirando.value = null
}

export async function cargarNudo(): Promise<void> {
  try {
    const d = obj(await invocar('nudo_estado'))
    nudoPrendido.value = typeof d?.prendido === 'boolean' ? d.prendido : null
  } catch {
    nudoPrendido.value = null
  }
}

export function puedeMostrar(e: EstadoReunionFront, prendido: boolean | null, enEspera: string | null): { ok: boolean; motivo?: string } {
  if (prendido === false) return { ok: false, motivo: 'Prendé el nudo en la bandeja' }
  if (e.ocupado || e.lineas.some((l) => l.respuesta?.estado === 'buscando' || l.respuesta?.estado === 'en_cola')) {
    return { ok: false, motivo: 'El Copiloto está ocupado' }
  }
  if (e.copiloto !== 'listo') return { ok: false, motivo: 'El Copiloto todavía no está listo' }
  if (e.estado === 'sin_pc') return { ok: false, motivo: 'Perdí la conexión con la PC' }
  if (e.estado === 'llena') return { ok: false, motivo: 'La reunión está llena: tocá Terminar' }
  if (e.estado !== 'escuchando' && e.estado !== 'pausada') return { ok: false, motivo: 'La reunión se está guardando' }
  if (enEspera !== null) return { ok: false }
  return { ok: true }
}

export async function mostrarAhora(pregunta: string): Promise<void> {
  const id = reunion.value.reunion
  const invoke = window.__TAURI__?.core?.invoke
  if (!id || mirando.value !== null) return
  errorReunion.value = null
  terminadasEnVuelo.clear()
  mirandoDe = id
  mirando.value = 'capturando'
  if (typeof invoke !== 'function') {
    errorReunion.value = MENSAJE_MOSTRAR.fallo
    mirando.value = null
    return
  }
  const r = await mostrar({ invoke, post: (url, body) => pedir('POST', url, body), reunion: id, device, pregunta })
  const yaTermino = r.ok && terminadasEnVuelo.has(r.linea)
  terminadasEnVuelo.clear()
  if (r.ok) {
    // Si la reunión cambió o terminó mientras tanto, o la respuesta ya llegó, no queda esperando.
    mirando.value = yaTermino || mirandoDe !== id || reunion.value.reunion !== id || !enCurso(reunion.value) ? null : r.linea
    return
  }
  errorReunion.value = MENSAJE_MOSTRAR[r.error]
  mirando.value = null
  if (r.error === 'apagado') nudoPrendido.value = false
}

/** Reunión que todavía espera un Terminar: en curso o llena (que el back guarda al cerrarla). */
function puedeCerrar(): boolean {
  const r = reunion.value
  return !!r.reunion && ['escuchando', 'pausada', 'sin_pc', 'llena'].includes(r.estado)
}

export function alLector(estado: EstadoLector, motivo?: string) {
  let cajitaAcoplada = reunion.value.cajitaAcoplada
  if (motivo === 'cajita_acoplada') cajitaAcoplada = true
  else if (motivo === 'cajita_escondida' || estado === 'apagado') cajitaAcoplada = false
  reunion.value = { ...reunion.value, lector: estado, cajitaAcoplada }
  if (estado === 'apagado' && motivo === 'bandeja' && puedeCerrar()) void terminar(true)
}

/** Después de guardar: vuelve al selector para empezar otra. */
export function nuevaReunion() {
  reunion.value = { ...inicial(), lector: reunion.value.lector }
  mirando.value = null
  errorReunion.value = null
  void cargarRepos()
}

export async function cargarRepos(): Promise<void> {
  try {
    const d = obj(await pedir('GET', '/api/reunion/repos'))
    const lista = Array.isArray(d?.repos) ? d.repos : []
    repos.value = lista
      .map(obj)
      .filter((r): r is Record<string, unknown> => r !== null && typeof r.ruta === 'string' && typeof r.nombre === 'string')
      .map((r) => ({ ruta: r.ruta as string, nombre: r.nombre as string }))
    rutaTodos.value = typeof d?.todos === 'string' ? d.todos : ''
  } catch {
    // Sin la lista queda lo anterior; "Todos" sigue funcionando.
  }
}

export async function cargarEstado(): Promise<void> {
  try {
    const snap = await pedir('GET', '/api/reunion/estado')
    const nuevo = desdeSnapshot(snap, reunion.value.lector)
    // Tras guardar, el back ya no tiene la reunión: el aviso de "guardada" se queda hasta la próxima.
    if (nuevo.reunion === null && reunion.value.estado === 'guardada') {
      soltarMirando()
      return
    }
    // El lector avisa de la cajita acoplada una sola vez: si es la misma reunión, el aviso sigue.
    if (nuevo.reunion !== null && nuevo.reunion === reunion.value.reunion) nuevo.cajitaAcoplada = reunion.value.cajitaAcoplada
    reunion.value = nuevo
    soltarMirandoSegunSnapshot()
  } catch {
    // Offline: queda el estado anterior.
  }
}

/** El SSE volvió: se pide el estado de nuevo y, si todo sigue escuchando, se manda lo que quedó en la cola. */
export async function alReconectar(): Promise<void> {
  await cargarEstado()
  if (reunion.value.estado === 'escuchando' && reunion.value.lector === 'escuchando') void lector?.vaciar()
}

export async function escuchar(reposElegidos: string[], todos: boolean, tema = ''): Promise<void> {
  errorReunion.value = null
  let id: string
  try {
    const d = obj(await pedir('POST', '/api/reunion/empezar', { device, repos: todos ? [] : reposElegidos, todos, tema }))
    if (typeof d?.reunion !== 'string' || !d.reunion) throw new Error('respuesta')
    id = d.reunion
    reunion.value = aplicarEvento({ ...reunion.value, reunion: null, estado: 'inactiva' }, 'reunion-estado', {
      reunion: id,
      estado: d.estado ?? 'escuchando',
      tope: false,
      solo_a_mano: reunion.value.soloAMano,
      detecciones: 0,
      tope_detecciones: reunion.value.topeDetecciones,
      copiloto: 'abriendo',
    })
  } catch (e) {
    errorReunion.value = mensajeDe(e, 'No pude empezar la reunión. Probá de nuevo.')
    return
  }
  try {
    const l = await invocar('reunion_escuchar')
    if (enLista(['escuchando', 'sin_subtitulos', 'pausado', 'apagado'] as const, l)) {
      reunion.value = { ...reunion.value, lector: l }
    }
  } catch {
    errorReunion.value = 'No pude abrir el lector de subtítulos. Cerré la reunión.'
    await postear('/api/reunion/terminar', { reunion: id }).catch(() => undefined)
  }
}

/** Marca la respuesta de una línea mientras el back trabaja; no pisa una respuesta lista que llegó antes. */
function marcarRespuesta(id: string, linea: string, estado: 'buscando' | 'en_cola', soloSiLibre = false) {
  if (reunion.value.reunion !== id) return
  const i = reunion.value.lineas.findIndex((l) => l.id === linea)
  if (i < 0) return
  const actual = reunion.value.lineas[i].respuesta
  if (soloSiLibre && actual && actual.estado !== 'error') return
  if (!soloSiLibre && actual?.estado === 'lista') return
  const lineas = reunion.value.lineas.slice()
  lineas[i] = { ...lineas[i], respuesta: { estado, texto: '', archivos: [] } }
  reunion.value = { ...reunion.value, lineas }
}

export async function tocar(linea: string): Promise<void> {
  const id = reunion.value.reunion
  if (!id) return
  errorReunion.value = null
  marcarRespuesta(id, linea, 'buscando', true)
  try {
    const d = obj(await pedir('POST', '/api/reunion/tocar', { reunion: id, linea }))
    if (d?.estado === 'en_cola') marcarRespuesta(id, linea, 'en_cola')
  } catch (e) {
    errorReunion.value = mensajeDe(e, 'No pude mandar la pregunta al Copiloto.')
  }
}

export async function descartar(linea: string): Promise<void> {
  const id = reunion.value.reunion
  if (!id) return
  errorReunion.value = null
  try {
    await pedir('POST', '/api/reunion/descartar', { reunion: id, linea })
    reunion.value = aplicarEvento(reunion.value, 'reunion-descartada', { reunion: id, linea })
  } catch (e) {
    errorReunion.value =
      e instanceof ErrorHttp && e.status === 409
        ? 'El Copiloto está buscando esa línea. Esperá que termine para descartarla.'
        : 'No pude descartar la línea.'
  }
}

export async function anotar(linea: string): Promise<void> {
  const id = reunion.value.reunion
  if (!id) return
  errorReunion.value = null
  try {
    const d = obj(await pedir('POST', '/api/reunion/anotar', { reunion: id, linea }))
    reunion.value = aplicarEvento(reunion.value, 'reunion-anotada', { reunion: id, linea, nota: d?.nota })
  } catch {
    errorReunion.value = 'No pude anotar la línea.'
  }
}

/** Ids de las líneas que se están guardando en la memoria de trabajo. */
export const guardandoMemoria = ref<string[]>([])

export async function guardarEnMemoria(linea: string): Promise<void> {
  const id = reunion.value.reunion
  if (!id || guardandoMemoria.value.includes(linea)) return
  errorReunion.value = null
  guardandoMemoria.value = [...guardandoMemoria.value, linea]
  try {
    await pedir('POST', '/api/reunion/memoria', { reunion: id, linea })
    reunion.value = aplicarEvento(reunion.value, 'reunion-memoria', { reunion: id, linea })
  } catch {
    errorReunion.value = 'No pude guardar en tu memoria de trabajo.'
  } finally {
    guardandoMemoria.value = guardandoMemoria.value.filter((x) => x !== linea)
  }
}

export async function preguntarUltimo(): Promise<void> {
  const id = reunion.value.reunion
  if (!id) return
  errorReunion.value = null
  try {
    await postear('/api/reunion/preguntar-ultimo', { reunion: id })
  } catch (e) {
    errorReunion.value = mensajeDe(e, 'No pude preguntar por lo último.')
  }
}

async function cambiarPausa(ruta: 'pausar' | 'seguir', cmd: string): Promise<void> {
  const id = reunion.value.reunion
  if (!id) return
  errorReunion.value = null
  try {
    await postear(`/api/reunion/${ruta}`, { reunion: id })
  } catch (e) {
    errorReunion.value = mensajeDe(e, 'No pude cambiar la pausa.')
    return
  }
  try {
    const l = await invocar(cmd)
    if (enLista(['escuchando', 'sin_subtitulos', 'pausado', 'apagado'] as const, l)) reunion.value = { ...reunion.value, lector: l }
  } catch {
    // El back ya quedó en pausa o siguiendo; el lector avisa su estado solo.
  }
}

export const pausar = () => cambiarPausa('pausar', 'reunion_pausar')
export const seguir = () => cambiarPausa('seguir', 'reunion_seguir')

let cerrando = false
let enVentana = false

/** En la ventana "Reunión" no hay lector: el cierre se le pide al notch, que vuelca su cola de texto. */
export function fijarEnVentana(v: boolean) {
  enVentana = v
}

/** Cierra la reunión: el lector vuelca su última tanda, la cola sale y recién entonces el back guarda. */
export async function terminar(sinInvoke = false): Promise<void> {
  const id = reunion.value.reunion
  if (!id || cerrando) return
  if (enVentana) {
    emitir('reunion-terminar-pedido')
    return
  }
  cerrando = true
  errorReunion.value = null
  try {
    if (!sinInvoke) await invocar('reunion_terminar').catch(() => undefined)
    await lector?.vaciar().catch(() => undefined)
    // Lo que no pudo salir (por ejemplo un post fallido) no puede colarse en otra reunión.
    lector?.descartar()
    await postear('/api/reunion/terminar', { reunion: id })
  } catch (e) {
    errorReunion.value = mensajeDe(e, 'No pude cerrar la reunión. Probá de nuevo.')
  } finally {
    cerrando = false
  }
}

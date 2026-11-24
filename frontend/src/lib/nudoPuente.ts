export type OpNudo = 'controles' | 'senalar' | 'marcar' | 'limpiar' | 'estado' | 'senalar_zona' | 'marcar_zonas'

export interface OrdenNudo {
  id: string
  token: string
  op: OpNudo
  args: Record<string, unknown>
  sesion: string
  guia: boolean
}

export const COMANDOS: Record<OpNudo, string> = {
  controles: 'nudo_controles',
  senalar: 'nudo_senalar',
  marcar: 'nudo_marcar',
  limpiar: 'nudo_limpiar',
  estado: 'nudo_estado',
  senalar_zona: 'nudo_senalar_zona',
  marcar_zonas: 'nudo_marcar_zonas',
}

const ERRORES_PC = new Set(['apagado', 'sin_ventana', 'sin_controles', 'foto_vieja', 'sin_control', 'invalido', 'fallo_pc'])
const ID_RE = /^[A-Za-z0-9_-]{8,64}$/

export type Invoke = (cmd: string, args?: Record<string, unknown>) => Promise<unknown>
type Post = (url: string, body: unknown) => Promise<unknown>

export function normalizarOrdenNudo(raw: unknown): OrdenNudo | null {
  if (!raw || typeof raw !== 'object') return null
  const o = raw as Record<string, unknown>
  if (typeof o.id !== 'string' || !ID_RE.test(o.id)) return null
  if (typeof o.token !== 'string' || !ID_RE.test(o.token)) return null
  if (typeof o.op !== 'string' || !Object.hasOwn(COMANDOS, o.op)) return null
  const args = o.args && typeof o.args === 'object' && !Array.isArray(o.args) ? (o.args as Record<string, unknown>) : {}
  return { id: o.id, token: o.token, op: o.op as OpNudo, args, sesion: typeof o.sesion === 'string' ? o.sesion : '', guia: o.guia === true }
}

function argumentosBase(orden: OrdenNudo): Record<string, unknown> | undefined {
  const { args, sesion } = orden
  if (orden.op === 'senalar') {
    const a: Record<string, unknown> = { foto: args.foto, n: args.n, texto: args.texto, sesion }
    if (args.esperar !== undefined && args.esperar !== null) a.esperar = args.esperar
    return a
  }
  if (orden.op === 'marcar') return { foto: args.foto, marcas: args.marcas, sesion }
  if (orden.op === 'senalar_zona') return { foto: args.foto, zona: args.zona, texto: args.texto, sesion }
  if (orden.op === 'marcar_zonas') return { foto: args.foto, zonas: args.zonas, sesion }
  return undefined
}

function argumentos(orden: OrdenNudo): Record<string, unknown> | undefined {
  const a = argumentosBase(orden)
  return a && orden.guia ? { ...a, guia: true } : a
}

const codigoPc = (e: unknown) => (typeof e === 'string' && ERRORES_PC.has(e) ? e : 'fallo_pc')

export async function atenderOrdenNudo(orden: OrdenNudo, device: string, deps: { invoke: Invoke; post: Post }): Promise<void> {
  let resultado: unknown
  try {
    const r = await deps.invoke(COMANDOS[orden.op], argumentos(orden))
    resultado = orden.op === 'controles' || orden.op === 'estado' ? r : { resultado: r }
  } catch (e) {
    resultado = { error: codigoPc(e) }
  }
  try {
    await deps.post(`/api/nudo/${orden.id}/respuesta`, { device, token: orden.token, resultado })
  } catch (e) {
    // El backend vence el pedido solo; acá queda el rastro para quien mire la consola.
    console.warn('[nudo] no se pudo mandar la respuesta', orden.op, e)
  }
}

/** true si quedó escuchando `nudo-salir`; false si no se pudo (el llamador puede reintentar con la próxima orden). */
export async function escucharSalirNudo(device: string, deps: { listen?: (e: string, cb: () => void) => unknown; post: Post }): Promise<boolean> {
  if (typeof deps.listen !== 'function') return false
  try {
    await deps.listen('nudo-salir', () => {
      void Promise.resolve(deps.post('/api/nudo/salir', { device })).catch((e) => console.warn('[nudo] no se pudo avisar la salida', e))
    })
    return true
  } catch (e) {
    console.warn('[nudo] no se pudo escuchar nudo-salir', e)
    return false
  }
}

export async function postJson(url: string, body: unknown): Promise<void> {
  const res = await fetch(url, {
    method: 'POST',
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(String(res.status))
}

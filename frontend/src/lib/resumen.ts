import type { Propuesta, ResumenSemanal, Seguimiento } from '../api/types'

const obj = (v: unknown): Record<string, any> => (v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, any>) : {})
const str = (v: unknown): string => (typeof v === 'string' ? v : '')
const num = (v: unknown): number | undefined => (typeof v === 'number' && Number.isFinite(v) ? v : undefined)
const suma = (v: unknown): number => Object.values(obj(v)).reduce<number>((a, n) => a + (num(n) ?? 0), 0)

function propuesta(v: unknown): Propuesta | null {
  const o = obj(v)
  const id = str(o.id)
  const texto = str(o.texto)
  if (!id || !texto) return null
  const m = obj(o.metrica)
  return {
    id, texto,
    ...(o.regla ? { regla: str(o.regla) } : {}),
    ...(o.clave ? { clave: str(o.clave) } : {}),
    ...(o.metrica ? { metrica: { nombre: str(m.nombre) || undefined, valor: num(m.valor) } } : {}),
    ...(num(o.peso) !== undefined ? { peso: num(o.peso) } : {}),
    ...(o.volvio === true ? { volvio: true } : {}),
  }
}

const TENDENCIAS = ['bajo', 'subio', 'igual']

function seguimiento(v: unknown): Seguimiento | null {
  const p = propuesta(v)
  if (!p) return null
  const o = obj(v)
  return { id: p.id, texto: p.texto, base: num(o.base) ?? null, valor: num(o.valor) ?? null, tendencia: TENDENCIAS.includes(o.tendencia) ? o.tendencia : undefined }
}

const lista = <T>(v: unknown, f: (x: unknown) => T | null): T[] => (Array.isArray(v) ? v.map(f).filter((x): x is T => x !== null) : [])

/** Lee el JSON del resumen semanal sin romper si falta una sección; null si no es un objeto. */
export function toResumen(raw: string): ResumenSemanal | null {
  let d: unknown
  try {
    d = JSON.parse(raw)
  } catch {
    return null
  }
  if (!d || typeof d !== 'object' || Array.isArray(d)) return null
  const o = obj(d)
  const p = obj(o.propuestas)
  return {
    semana: str(o.semana),
    desde: str(o.desde),
    hasta: str(o.hasta),
    resumen: obj(o.resumen),
    propuestas: {
      nuevas: lista(p.nuevas, propuesta),
      mas_adelante: lista(p.mas_adelante, propuesta),
      seguimiento: lista(p.seguimiento, seguimiento),
      volvio: lista(p.volvio, propuesta),
    },
  }
}

export interface SeccionResumen {
  clave: string
  titulo: string
  numero: number
  frase: string
}

const veces = (n: number, uno: string, varios: string) => `${n} ${n === 1 ? uno : varios}`

/** Una línea por sección del resumen: el número grande y una frase. Las que faltan dan 0. */
export function seccionesDe(r: ResumenSemanal): SeccionResumen[] {
  const s = obj(r.resumen)
  const top = Array.isArray(s.errores?.top) ? s.errores.top : []
  const errores = top.reduce((a: number, e: any) => a + (num(e?.n) ?? 0), 0)
  const pedidos = suma(s.pedidos?.por_tipo)
  const sinRespuesta = num(s.respuesta?.sin_respuesta) ?? 0
  const trabas = suma(s.trabas?.por_tipo)
  const corridos = num(s.comandos?.corridos) ?? 0
  const fallaron = suma(s.comandos?.fallos)
  const noCorridos = num(s.comandos?.no) ?? 0
  const frenados = num(s.cierres?.frenados) ?? 0
  const pct = num(s.cierres?.resueltos_pct)
  const appErrores = suma(s.app?.errores)
  const tuneles = num(s.app?.tuneles_fallidos) ?? 0
  const desconexiones = num(s.app?.desconexiones) ?? 0
  const seguidas = (r.propuestas?.seguimiento ?? []).length
  return [
    { clave: 'errores', titulo: 'Errores', numero: errores, frase: errores ? `veces se repitieron los errores más comunes (${veces(top.length, 'distinto', 'distintos')})` : 'No hubo errores repetidos' },
    { clave: 'pedidos', titulo: 'Pedidos', numero: pedidos, frase: pedidos ? 'pedidos de Claude que pasaron por la app' : 'No hubo pedidos' },
    { clave: 'respuesta', titulo: 'Respuesta', numero: sinRespuesta, frase: sinRespuesta ? 'avisos que quedaron sin respuesta' : 'Todos los avisos tuvieron respuesta' },
    { clave: 'trabas', titulo: 'Trabas', numero: trabas, frase: trabas ? 'veces que una sesión quedó trabada' : 'No hubo trabas' },
    { clave: 'comandos', titulo: 'Comandos', numero: corridos, frase: `comandos corridos; ${veces(fallaron, 'falló', 'fallaron')} y ${veces(noCorridos, 'se rechazó', 'se rechazaron')}` },
    { clave: 'cierres', titulo: 'Cierres', numero: frenados, frase: frenados ? `cierres frenados${pct === undefined ? '' : `; se resolvió el ${pct}%`}` : 'No se frenó ningún cierre' },
    { clave: 'app', titulo: 'App', numero: appErrores, frase: `errores de la app; ${veces(tuneles, 'túnel fallido', 'túneles fallidos')} y ${veces(desconexiones, 'desconexión', 'desconexiones')}` },
    { clave: 'seguimiento', titulo: 'Seguimiento', numero: seguidas, frase: seguidas ? 'propuestas que estás siguiendo' : 'Nada en seguimiento' },
  ]
}

export interface LineaDetalle {
  etiqueta: string
  valor: string
}

const seg = (s: unknown): string => {
  const n = num(s)
  if (n === undefined) return '—'
  return n < 60 ? `${Math.round(n)} s` : `${Math.round(n / 60)} min`
}

const ESTADOS: Record<string, string> = { rechazado: 'Rechazados', vencido: 'Vencidos', descartado: 'Descartados' }
const CANALES: Record<string, string> = { en_app: 'en la app', celu: 'en el celu' }
const AVISOS: Record<string, string> = { asks: 'Preguntas', blocked: 'Frenos' }

const cuentas = (v: unknown, etiqueta: (k: string) => string): LineaDetalle[] =>
  Object.entries(obj(v)).map(([k, n]) => ({ etiqueta: etiqueta(k), valor: String(num(n) ?? 0) }))

/** Lista corta "etiqueta: valor" de lo que trae el resumen para una sección; vacía si no hay nada. */
export function detalleDe(clave: string, resumen: Record<string, any>): LineaDetalle[] {
  const s = obj(resumen)
  switch (clave) {
    case 'pedidos': {
      const p = obj(s.pedidos)
      const lineas = cuentas(p.por_tipo, (k) => `Pedidos de ${k}`)
      for (const [estado, motivos] of Object.entries(obj(p.por_motivo))) {
        for (const [motivo, n] of Object.entries(obj(motivos))) {
          lineas.push({ etiqueta: `${ESTADOS[estado] ?? estado} (${motivo})`, valor: String(num(n) ?? 0) })
        }
      }
      if (num(p.mediana_s) !== undefined) lineas.push({ etiqueta: 'Tiempo típico', valor: seg(p.mediana_s) })
      return lineas
    }
    case 'respuesta': {
      const r = obj(s.respuesta)
      const lineas: LineaDetalle[] = []
      for (const [aviso, nombre] of Object.entries(AVISOS)) {
        for (const [canal, donde] of Object.entries(CANALES)) {
          const g = obj(obj(r[aviso])[canal])
          if (!num(g.n)) continue
          lineas.push({ etiqueta: `${nombre} ${donde}`, valor: `mediana ${seg(g.mediana_s)}, 9 de cada 10 en ${seg(g.p90_s)} (${g.n})` })
        }
      }
      lineas.push({ etiqueta: 'Sin respuesta', valor: String(num(r.sin_respuesta) ?? 0) })
      return lineas
    }
    case 'trabas': {
      const t = obj(s.trabas)
      const lineas = cuentas(t.por_tipo, (k) => `Trabas de ${k}`)
      if (num(t.mediana_s) !== undefined) lineas.push({ etiqueta: 'Duración típica', valor: seg(t.mediana_s) })
      return [...lineas, ...cuentas(t.por_fin, (k) => `Terminaron: ${k}`)]
    }
    case 'comandos': {
      const c = obj(s.comandos)
      return [
        { etiqueta: 'Corridos', valor: String(num(c.corridos) ?? 0) },
        ...cuentas(c.fallos, (k) => `Fallaron con código ${k}`),
        { etiqueta: 'Rechazados', valor: String(num(c.no) ?? 0) },
      ]
    }
    case 'cierres': {
      const c = obj(s.cierres)
      const pct = num(c.resueltos_pct)
      return [
        { etiqueta: 'Frenados', valor: String(num(c.frenados) ?? 0) },
        ...(pct === undefined ? [] : [{ etiqueta: 'Resueltos', valor: `${pct}%` }]),
      ]
    }
    case 'app': {
      const a = obj(s.app)
      return [
        ...cuentas(a.errores, (k) => `Errores ${k}`),
        { etiqueta: 'Túneles fallidos', valor: String(num(a.tuneles_fallidos) ?? 0) },
        { etiqueta: 'Desconexiones', valor: String(num(a.desconexiones) ?? 0) },
      ]
    }
    default:
      return []
  }
}

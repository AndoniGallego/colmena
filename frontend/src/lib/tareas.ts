export type Agente = 'claude' | 'cursor'
export type TipoCuando = 'diaria' | 'dias' | 'semanal'

export interface Cuando {
  tipo: TipoCuando
  hora: string
  dias?: number[]
  dia?: number | null
}

export interface FormPrograma {
  nombre: string
  repo: string
  pedido: string
  agente: Agente
  modelo: string
  tipo: TipoCuando
  hora: string
  dias: number[]
  dia: number
}

export interface CuerpoPrograma {
  nombre: string
  repo: string
  pedido: string
  agente: Agente
  modelo: string
  cuando: Cuando
}

/** El SSE de api/http.ts lo dispara cuando el backend avisa un cambio en las tareas programadas. */
export const EVENTO_PROGRAMADAS = 'orq:programadas'
/** Igual, cuando cambia un trabajador de Cursor (evento SSE `cursor`). */
export const EVENTO_CURSOR = 'orq:cursor'
export const MAX_PEDIDO = 3800
export const MAX_NOMBRE = 60
export const DIAS_CORTOS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom']
export const DIAS_LETRA = ['L', 'M', 'M', 'J', 'V', 'S', 'D']
const DIAS_PLURAL = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábados', 'domingos']
const HORA_RE = /^([01]\d|2[0-3]):[0-5]\d$/
const MODELO_RE = /^[A-Za-z0-9][A-Za-z0-9._:/-]{0,79}$/

export function cuandoTexto(c: Cuando): string {
  if (c.tipo === 'diaria') return `Todos los días a las ${c.hora}`
  if (c.tipo === 'semanal') return `Los ${DIAS_PLURAL[c.dia ?? 0] ?? ''} a las ${c.hora}`
  const n = [...(c.dias ?? [])].sort((a, b) => a - b).map((d) => DIAS_CORTOS[d] ?? '')
  const union = n.length <= 1 ? (n[0] ?? '') : `${n.slice(0, -1).join(', ')} y ${n[n.length - 1]}`
  return `${union} a las ${c.hora}`
}

const dos = (n: number) => String(n).padStart(2, '0')

/** `proxima` en epoch (segundos); null = pausada. */
export function proximaTexto(proxima: number | null, ahora: number = Date.now() / 1000): string {
  if (proxima == null) return 'Pausada'
  const d = new Date(proxima * 1000)
  const hoy = new Date(ahora * 1000)
  const hora = `${dos(d.getHours())}:${dos(d.getMinutes())}`
  const dia0 = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime()
  const dif = Math.round((dia0(d) - dia0(hoy)) / 86400000)
  if (dif === 0) return `Hoy ${hora}`
  if (dif === 1) return `Mañana ${hora}`
  const sem = DIAS_CORTOS[(d.getDay() + 6) % 7]
  return `${sem} ${dos(d.getDate())}/${dos(d.getMonth() + 1)} ${hora}`
}

export function validarPrograma(f: FormPrograma, cursorDisponible: boolean): string {
  if (!f.nombre.trim()) return 'Ponele un nombre a la tarea.'
  if (!f.repo) return 'Elegí un repo.'
  if (!f.pedido.trim()) return 'Escribí el pedido.'
  if (f.pedido.length > MAX_PEDIDO) return `El pedido pasa los ${MAX_PEDIDO} caracteres.`
  if (!HORA_RE.test(f.hora)) return 'Poné una hora válida.'
  if (f.tipo === 'dias' && f.dias.length === 0) return 'Elegí al menos un día.'
  if (f.agente === 'cursor') {
    if (!cursorDisponible) return 'Cursor no está disponible en esta notebook.'
    if (f.modelo.trim() && !MODELO_RE.test(f.modelo.trim())) return 'El modelo tiene caracteres que no puedo usar.'
  }
  return ''
}

export function armarCuerpoPrograma(f: FormPrograma): CuerpoPrograma {
  const cuando: Cuando =
    f.tipo === 'dias' ? { tipo: 'dias', hora: f.hora, dias: [...f.dias].sort((a, b) => a - b) } : f.tipo === 'semanal' ? { tipo: 'semanal', hora: f.hora, dia: f.dia } : { tipo: 'diaria', hora: f.hora }
  return { nombre: f.nombre.trim(), repo: f.repo, pedido: f.pedido.trim(), agente: f.agente, modelo: f.agente === 'cursor' ? f.modelo.trim() : '', cuando }
}

export type IconoCorrida = 'check' | 'warn' | 'minus' | 'clock'

export function estadoCorrida(estado: string): { icono: IconoCorrida; etiqueta: string } {
  switch (estado) {
    case 'ok':
      return { icono: 'check', etiqueta: 'Corrió' }
    case 'fallo':
      return { icono: 'warn', etiqueta: 'Falló' }
    case 'salteada':
      return { icono: 'minus', etiqueta: 'Salteada' }
    case 'en_curso':
      return { icono: 'clock', etiqueta: 'En curso' }
    default:
      return { icono: 'minus', etiqueta: estado }
  }
}

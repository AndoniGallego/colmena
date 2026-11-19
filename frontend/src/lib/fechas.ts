const DIAS = ['domingo', 'lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado']
const MESES = ['enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio', 'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre']

const pad = (n: number) => String(n).padStart(2, '0')
export const ymd = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
export const hoyLocal = (now = Date.now()) => ymd(new Date(now))

function parse(fecha: string): Date {
  const [y, m, d] = fecha.split('-').map(Number)
  return new Date(y, m - 1, d, 12)
}

export function shiftFecha(fecha: string, days: number): string {
  const d = parse(fecha)
  d.setDate(d.getDate() + days)
  return ymd(d)
}

export const daysBetween = (a: string, b: string) => Math.round((parse(b).getTime() - parse(a).getTime()) / 86_400_000)

export function fechaLarga(fecha: string): string {
  const d = parse(fecha)
  const dia = DIAS[d.getDay()]
  return `${dia[0].toUpperCase()}${dia.slice(1)} ${d.getDate()} de ${MESES[d.getMonth()]}`
}

export function mondayOf(fecha: string): string {
  const d = parse(fecha)
  return shiftFecha(fecha, -((d.getDay() + 6) % 7))
}

const DIAS_CORTOS = ['dom', 'lun', 'mar', 'mié', 'jue', 'vie', 'sáb']
export const diaCorto = (fecha: string) => DIAS_CORTOS[parse(fecha).getDay()]
export const diaDelMes = (fecha: string) => parse(fecha).getDate()
export const mesCorto = (fecha: string) => MESES[parse(fecha).getMonth()].slice(0, 3)

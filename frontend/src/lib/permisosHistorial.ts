import type { RegistroPermiso } from '../api/types'

export interface FilaHistorial {
  hora: string
  quien: string
  decision: string
  herramienta: string
  detalle: string
  sesion: string
}

const QUIEN: Record<string, string> = {
  usuario: 'Vos',
  politica: 'Política (antes)',
  centinela: 'Centinela (antes)',
}

const DECISION: Record<NonNullable<RegistroPermiso['decision']>, string> = {
  permitir: 'Permitido',
  rechazar: 'Rechazado',
  siempre: 'Permitido siempre',
}

function horaTexto(iso?: string): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleString(undefined, { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function decisionTexto(it: RegistroPermiso): string {
  if (it.decision) return DECISION[it.decision]
  if (it.quien === 'politica' || it.quien === 'centinela') return 'Aprobado'
  if (it.categoria === 'usuario') return 'Te preguntó'
  return '—'
}

function detalleTexto(entrada: RegistroPermiso['entrada']): string {
  if (!entrada || typeof entrada !== 'object') return ''
  if (typeof entrada.command === 'string') return entrada.command
  if (typeof entrada.file_path === 'string') return entrada.file_path
  return ''
}

function sesionTexto(it: RegistroPermiso): string {
  if (it.sesion) return it.sesion
  const sid = it.session_id ?? ''
  return sid ? sid.slice(0, 8) : '—'
}

export function filasHistorial(items: RegistroPermiso[]): FilaHistorial[] {
  return items.map((it) => ({
    hora: horaTexto(it.hora),
    quien: (it.quien && Object.hasOwn(QUIEN, it.quien) ? QUIEN[it.quien] : '—'),
    decision: decisionTexto(it),
    herramienta: typeof it.herramienta === 'string' ? it.herramienta : '',
    detalle: detalleTexto(it.entrada),
    sesion: sesionTexto(it),
  }))
}

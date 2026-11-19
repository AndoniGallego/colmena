import type { EstadoPedido, PedidoPermiso } from '../api/types'

export const MENSAJE_ESTADO: Partial<Record<EstadoPedido, string>> = {
  enviando: 'Mandando la respuesta…',
  permitido: 'Permitido',
  rechazado: 'Rechazado',
  siempre: 'Permitido siempre',
  terminal: 'Resuelto en la terminal',
  vencido: 'Se contesta en el diálogo',
  dialogo: 'Se contesta en el diálogo',
}

function asText(value: unknown): string {
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

function bloqueAntesDespues(antes: unknown, despues: unknown): string {
  return `Antes\n${asText(antes)}\n\nDespués\n${asText(despues)}`
}

export function detalleEntrada(pedido: Pick<PedidoPermiso, 'herramienta' | 'entrada'>): string {
  const { herramienta, entrada } = pedido

  if (herramienta === 'Edit') {
    const path = entrada.file_path != null ? asText(entrada.file_path) : ''
    const cuerpo = bloqueAntesDespues(entrada.old_string, entrada.new_string)
    return path ? `${path}\n\n${cuerpo}` : cuerpo
  }

  if (herramienta === 'MultiEdit') {
    const path = entrada.file_path != null ? `${asText(entrada.file_path)}\n\n` : ''
    const edits = Array.isArray(entrada.edits) ? entrada.edits : []
    const partes = edits.map((ed, i) => {
      const e = ed && typeof ed === 'object' ? (ed as Record<string, unknown>) : {}
      const head = edits.length > 1 ? `Edición ${i + 1}\n` : ''
      return `${head}${bloqueAntesDespues(e.old_string, e.new_string)}`
    })
    return `${path}${partes.join('\n\n')}`.trimEnd()
  }

  if (herramienta === 'Write') {
    const path = entrada.file_path != null ? `${asText(entrada.file_path)}\n\n` : ''
    return `${path}${asText(entrada.content)}`.trimEnd()
  }

  if (herramienta === 'ExitPlanMode') {
    return asText(entrada.plan)
  }

  if (herramienta === 'Bash') {
    const lines: string[] = []
    if (entrada.command != null) lines.push(asText(entrada.command))
    if (entrada.description != null) lines.push(asText(entrada.description))
    if (lines.length) return lines.join('\n\n')
  }

  return JSON.stringify(entrada, null, 2)
}

export function resumenRegistro(item: { herramienta?: string; entrada?: Record<string, unknown> }): string {
  const herramienta = item.herramienta ?? ''
  const entrada = item.entrada ?? {}
  if (herramienta === 'Bash' && typeof entrada.command === 'string') return entrada.command
  if (['Read', 'Edit', 'Write'].includes(herramienta) && typeof entrada.file_path === 'string') return entrada.file_path
  const corto = detalleEntrada({ herramienta, entrada }).split('\n')[0]?.trim()
  return corto || herramienta || '—'
}

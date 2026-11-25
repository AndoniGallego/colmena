import type { Propuesta } from '../api/types'
import { MAX_TAREA } from './nuevaTerminal'

const PEDIDO = 'Armar diseño y plan antes de tocar código; no cambiar nada sin mi OK.'

export function briefPropuesta(p: Propuesta, semana: string): string {
  const m = p.metrica
  const metrica = m?.nombre ? `Métrica: ${m.nombre} = ${m.valor ?? 'sin dato'}` : ''
  const cola = [metrica, PEDIDO].filter(Boolean).join('\n')
  const cabeza = `Propuesta del resumen de la semana ${semana}: ${p.texto}`
  return `${cabeza.slice(0, MAX_TAREA - cola.length - 1)}\n${cola}`
}

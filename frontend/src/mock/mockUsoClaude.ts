import type { DiosDia, DiosTokens } from '../api/types'
import type { ClaudeUso, UsoAgrupar, UsoFila, UsoRango } from '../lib/usoClaude'

const tk = (n: number): DiosTokens => ({ input: Math.round(n * 0.01), cache_write: Math.round(n * 0.06), cache_read: Math.round(n * 0.9), output: Math.round(n * 0.03), mensajes: Math.ceil(n / 400_000), total: n })

const SESIONES = [
  ['Arreglar el login de la tienda', 'tienda-web', 0.31],
  ['diseño · Colmena', 'orquestador', 0.22],
  ['Revisar MR del carrito', 'tienda-web', 0.14],
  ['Migrar la base de datos', 'api-pagos', 0.1],
  ['Planificar la semana', 'notas', 0.07],
  ['Probar el instalador', 'kit', 0.05],
] as const

function filas(total: number, agrupar: UsoAgrupar): UsoFila[] {
  const rest = total
  if (agrupar === 'modelos') {
    const mods: UsoFila[] = [
      { id: 'claude-opus-5-5', nombre: 'Opus 5.5', detalle: 'claude-opus-5-5', tipo: '', ...tk(Math.round(rest * 0.62)) },
      { id: 'claude-sonnet-5-5', nombre: 'Sonnet 5.5', detalle: 'claude-sonnet-5-5', tipo: '', ...tk(Math.round(rest * 0.33)) },
      { id: 'claude-haiku-5-5', nombre: 'Haiku 5.5', detalle: 'claude-haiku-5-5', tipo: '', ...tk(Math.round(rest * 0.05)) }
    ]
    return mods.sort((a, b) => b.total - a.total)
  }
  if (agrupar === 'proyectos') {
    const by = new Map<string, number>()
    for (const [, p, f] of SESIONES) by.set(p, (by.get(p) ?? 0) + f)
    const out: UsoFila[] = [...by].map(([p, f]) => ({ id: p, nombre: p, detalle: '', tipo: '', ...tk(Math.round(rest * f)) }))
    out.push({ id: '_otras', nombre: 'Otras 3', detalle: '', tipo: 'otras', ...tk(Math.round(rest * 0.11)) })
    return out.sort((a, b) => b.total - a.total)
  }
  const out: UsoFila[] = SESIONES.map(([nombre, p, f], i) => ({ id: `s${i}`, nombre, detalle: p, tipo: '', ...tk(Math.round(rest * f)) }))
  out.push({ id: '_otras', nombre: 'Otras 9', detalle: '', tipo: 'otras', ...tk(Math.round(rest * 0.11)) })
  return out.sort((a, b) => b.total - a.total)
}

export function mockClaudeUso(diosDias: DiosDia[], diosHoy: DiosTokens): ClaudeUso {
  const historial = diosDias.map((d, i) => ({ ...tk(d.total * 38 + (i % 4) * 9_000_000 + (d.total ? 4_000_000 : 0)), fecha: d.fecha }))
  const sum = (n: number) => historial.slice(-n).reduce((a, d) => a + d.total, 0)
  const span: Record<UsoRango, number> = { hoy: 1, '7d': 7, '30d': 30 }
  const totales = {} as ClaudeUso['totales']
  const desglose = {} as ClaudeUso['desglose']
  for (const r of Object.keys(span) as UsoRango[]) {
    const total = sum(span[r])
    totales[r] = tk(total)
    desglose[r] = { sesiones: filas(total, 'sesiones'), proyectos: filas(total, 'proyectos'), modelos: filas(total, 'modelos') }
  }
  const now = Date.now()
  return {
    generado: new Date(now).toISOString(),
    totales,
    historial,
    desglose,
    limites: {
      fiveHour: { pct: 63, resetsAt: new Date(now + (2 * 60 + 14) * 60_000).toISOString(), vencido: false },
      sevenDay: { pct: 38, resetsAt: new Date(now + 4.3 * 86_400_000).toISOString(), vencido: false },
      actualizado: new Date(now - 60_000).toISOString(),
    },
  }
}

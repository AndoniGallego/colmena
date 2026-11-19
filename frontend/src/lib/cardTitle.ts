import { plainPreview } from './preview'

export function esNombrePropioTab(label: string): boolean {
  const t = (label || '').trim()
  return t.length > 0 && !/^\d+$/.test(t)
}

export function tituloTarjeta(title: string | null | undefined, doing: string | null | undefined, tabLabelRaw: string): string {
  if (esNombrePropioTab(tabLabelRaw)) return tabLabelRaw.trim()
  return plainPreview(title) || plainPreview(doing) || 'Sin título'
}

export function ocultarNombreTab(agentCount: number, tabDisplayName: string, cardTitle: string): boolean {
  return agentCount === 1 && tabDisplayName === cardTitle
}

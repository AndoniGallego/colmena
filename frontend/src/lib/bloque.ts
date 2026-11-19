import type { Diagrama, Direccion } from './diagrama'
import { layoutDiagrama } from './diagramaLayout'
import { medirAprox, type Escena, type Medir } from './escena'
import { escenaProceso, escenaSecuencia } from './pasosEscena'

const NOMBRE_TIPO = { estructura: 'Diagrama', secuencia: 'Secuencia', proceso: 'Proceso' } as const

/** The label of a diagram's kind: "Diagrama", "Secuencia" or "Proceso". */
export const etiquetaDe = (d: Diagrama) => NOMBRE_TIPO[d.tipo]

export const tituloDe = (d: Diagrama) => d.titulo || etiquetaDe(d)

/** How much the scene must shrink to fit the room (1 = natural size or bigger room). */
export const escalaPara = (e: Escena, ancho: number, alto: number) => Math.min(1, ancho / e.w, alto / e.h)

/** Lays the diagram out; when no direction is asked for, the one that fits the room best wins. */
export function escenaDe(d: Diagrama, ancho: number, altoMax: number, medir: Medir = medirAprox): Escena {
  const compacto = ancho < 560
  if (d.tipo === 'secuencia') return escenaSecuencia(d, medir, compacto)
  if (d.tipo === 'estructura' && d.direccion) return layoutDiagrama(d, { direccion: d.direccion, medir, compacto })
  const hacer = (dir: Direccion) => (d.tipo === 'estructura' ? layoutDiagrama(d, { direccion: dir, medir, compacto }) : escenaProceso(d, dir, medir, compacto))
  const v = hacer('vertical')
  const h = hacer('horizontal')
  const sv = escalaPara(v, ancho, altoMax)
  const sh = escalaPara(h, ancho, altoMax)
  if (Math.abs(sv - sh) < 0.04) {
    if (d.tipo === 'proceso') return v
    return ancho >= 700 ? h : v
  }
  return sh > sv ? h : v
}

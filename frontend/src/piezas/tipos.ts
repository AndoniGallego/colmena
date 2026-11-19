import type { Component, Ref } from 'vue'
import type { Aviso } from '../api/types'
import type NavMark from '../components/NavMark.vue'
import type { IconoBuscador } from '../lib/buscador'

export type IconoSeccion = InstanceType<typeof NavMark>['$props']['name']

export interface SeccionPieza {
  titulo: string
  icono: IconoSeccion
  /** Vista de la sección (pane del pager en celu, capa en escritorio). */
  vista: Component
  /** Encendida mientras la sección está a la vista; prenderla la abre. */
  visible: Ref<boolean>
  /** Cambia cuando algo pide abrir la sección. */
  pedido?: Ref<unknown>
}

export interface EntradaSeccionPieza {
  titulo: string
  sub: string
  icono: IconoBuscador
  claves: string
}

export interface AccionPieza extends EntradaSeccionPieza {
  id: string
  correr: () => void
}

export interface AvisosPieza {
  kind: string
  icono: IconoBuscador
  etiqueta: string
  /** El ícono del aviso va con el color de acento. */
  acento?: boolean
  /** Hay algo abierto que ya muestra lo que dicen sus avisos. */
  abierto: () => boolean
  ir: (a: Aviso) => void
}

export interface NotificacionesPieza {
  pref: { key: string; label: string; hint: string }
  /** Manda el aviso de prueba a este dispositivo. */
  probar: (endpoint: string) => Promise<void>
  probarEtiqueta: string
  filaPrueba: { kind: string; label: string }
}

/** Una función opcional de la app: vive entera en `src/piezas/<nombre>/` y se suma por este contrato. */
export interface Pieza {
  /** Id de la vista y de la sección en el buscador. */
  id: string
  seccion?: SeccionPieza
  overlay?: Component
  init?: () => void
  alEntrar?: () => void | Promise<void>
  mock?: () => void | Promise<void>
  buscador?: { seccion?: EntradaSeccionPieza; acciones: AccionPieza[] }
  avisos?: AvisosPieza
  notificaciones?: NotificacionesPieza
}

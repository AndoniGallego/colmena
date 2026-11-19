import { NOMBRE_RE } from '../api/entornosApi'
import { ErrorUsuario } from './errores'
import './notchPuente'

export interface EstadoTunel {
  estado: 'abierto' | 'error'
  puertos: number[]
  error: string | null
}

export interface EstadoEntornos {
  notebook: string
  tuneles: Record<string, EstadoTunel>
}

export const SOLO_APP = 'Para abrir entornos usá la app de Windows'

export interface PuenteEntornos {
  enPrograma: boolean
  estado(): Promise<EstadoEntornos>
  abrir(nombre: string, puertos: number[], principal: number): Promise<EstadoTunel>
  cerrar(nombre: string): Promise<void>
  ajusteNotebook(): Promise<void>
}

function rechazoInvoke(e: unknown): ErrorUsuario {
  const msg = typeof e === 'string' ? e : e instanceof Error ? e.message : String(e)
  return new ErrorUsuario(msg)
}

export function crearPuenteEntornos(w: Window = window): PuenteEntornos {
  const invoke = w.__TAURI__?.core?.invoke
  const enPrograma = typeof invoke === 'function'

  return {
    enPrograma,
    async estado() {
      if (!enPrograma) return { notebook: '', tuneles: {} }
      try {
        return (await invoke!('entornos_estado')) as EstadoEntornos
      } catch (e) {
        throw rechazoInvoke(e)
      }
    },
    async abrir(nombre, puertos, principal) {
      if (!enPrograma) throw new ErrorUsuario(SOLO_APP)
      if (!NOMBRE_RE.test(nombre)) throw new ErrorUsuario('nombre inválido')
      try {
        return (await invoke!('entorno_abrir', { nombre, puertos, principal })) as EstadoTunel
      } catch (e) {
        throw rechazoInvoke(e)
      }
    },
    async cerrar(nombre) {
      if (!enPrograma) throw new ErrorUsuario(SOLO_APP)
      if (!NOMBRE_RE.test(nombre)) throw new ErrorUsuario('nombre inválido')
      try {
        await invoke!('entorno_cerrar', { nombre })
      } catch (e) {
        throw rechazoInvoke(e)
      }
    },
    async ajusteNotebook() {
      if (!enPrograma) throw new ErrorUsuario(SOLO_APP)
      try {
        await invoke!('abrir_ajuste_notebook')
      } catch (e) {
        throw rechazoInvoke(e)
      }
    },
  }
}

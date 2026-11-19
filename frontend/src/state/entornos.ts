import { reactive, ref, watch, type Ref } from 'vue'
import type { Entorno, ListadoEntornos } from '../api/entornosApi'
import { listarEntornos } from '../api/entornosApi'
import { detalleTecnico, mensajeError, mensajeErrorRed } from '../lib/errores'
import { puertosTunel } from '../lib/entornos'
import { crearPuenteEntornos, type EstadoTunel, type PuenteEntornos } from '../lib/entornosPuente'

export interface DepsEntornos {
  listar: () => Promise<ListadoEntornos>
  puente: PuenteEntornos
}

let deps: DepsEntornos | null = null

let pushed = false

export const entornosOpen: Ref<boolean> = ref(false)

export const entornos = reactive({
  enPrograma: false,
  notebook: '',
  lista: [] as Entorno[],
  error: '',
  errorDetalle: null as string | null,
  cargando: false,
  tuneles: {} as Record<string, EstadoTunel>,
  abriendo: [] as string[],
  cerrando: [] as string[],
  errores: {} as Record<string, string>,
})

export function setDepsEntornos(d: DepsEntornos): void {
  deps = d
}

function getDeps(): DepsEntornos {
  if (!deps) {
    deps = { listar: listarEntornos, puente: crearPuenteEntornos(window) }
  }
  return deps
}

export async function refrescarTuneles(): Promise<void> {
  const { puente } = getDeps()
  if (!puente.enPrograma) return
  try {
    const s = await puente.estado()
    entornos.notebook = s.notebook
    entornos.tuneles = { ...s.tuneles }
  } catch {
    /* no tocar */
  }
}

export async function cargarEntornos(): Promise<void> {
  entornos.cargando = true
  const { listar, puente } = getDeps()
  entornos.enPrograma = puente.enPrograma
  try {
    const r = await listar()
    entornos.lista = r.entornos
    entornos.error = r.error ?? ''
    entornos.errorDetalle = null
  } catch (e) {
    entornos.error = mensajeErrorRed(e)
    entornos.errorDetalle = detalleTecnico(e)
  }
  await refrescarTuneles()
  entornos.cargando = false
}

export async function abrirPuerto(e: Entorno, puerto: number): Promise<void> {
  const { puente } = getDeps()
  if (entornos.abriendo.includes(e.nombre)) return
  entornos.abriendo.push(e.nombre)
  delete entornos.errores[e.nombre]
  try {
    await puente.abrir(e.nombre, puertosTunel(e), puerto)
  } catch (err) {
    entornos.errores[e.nombre] = mensajeError(err)
  } finally {
    entornos.abriendo = entornos.abriendo.filter((n) => n !== e.nombre)
    await refrescarTuneles()
  }
}

export async function abrirEntorno(e: Entorno): Promise<void> {
  if (e.principal === null) return
  await abrirPuerto(e, e.principal)
}

export async function cerrarEntorno(nombre: string): Promise<void> {
  const { puente } = getDeps()
  if (entornos.cerrando.includes(nombre)) return
  entornos.cerrando.push(nombre)
  delete entornos.errores[nombre]
  try {
    await puente.cerrar(nombre)
  } catch (err) {
    entornos.errores[nombre] = mensajeError(err)
  } finally {
    entornos.cerrando = entornos.cerrando.filter((n) => n !== nombre)
    await refrescarTuneles()
  }
}

export function cambiarNotebook(): void {
  const { puente } = getDeps()
  void puente.ajusteNotebook().catch((e) => {
    entornos.error = mensajeError(e)
    entornos.errorDetalle = detalleTecnico(e)
  })
}

export function openEntornos(): void {
  if (entornosOpen.value) return
  history.pushState({ ...(history.state ?? {}), orqEntornos: true }, '')
  pushed = true
  entornosOpen.value = true
}

export function closeEntornos(): void {
  if (!entornosOpen.value) return
  if (pushed && history.state?.orqEntornos) history.back()
  else {
    pushed = false
    entornosOpen.value = false
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('popstate', () => {
    if (entornosOpen.value && !history.state?.orqEntornos) {
      entornosOpen.value = false
      pushed = false
    }
  })
}

if (typeof window !== 'undefined') {
  void import('./app').then(({ auth }) => {
    watch(auth, (a) => {
      if (a !== 'ready') {
        entornosOpen.value = false
        pushed = false
      }
    })
  })
}

export const esRutaEntornos = (pathname: string) => pathname === '/entornos' || pathname === '/entornos/'

export function abrirDesdeRuta(): void {
  if (!esRutaEntornos(location.pathname)) return
  history.replaceState(history.state, '', import.meta.env.BASE_URL + location.search + location.hash)
  openEntornos()
}

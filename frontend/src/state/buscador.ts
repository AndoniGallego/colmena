import { computed, ref, watch } from 'vue'
import { aplanar, buscar, construirCatalogo, inicial, sumarReciente, type Destino, type Entrada, type PiezasCatalogo, type Seccion, type Seccionado } from '../lib/buscador'
import { loadRecientes, saveRecientes } from '../lib/storage'
import { setTheme, theme } from '../lib/theme'
import { desktop } from '../lib/viewport'
import { auth, boardState, showOnBoard, viewRequest } from './app'
import { av, irAAviso } from './avisos'
import { libItems, libVisible, openInLibrary, openOverlay } from './biblioteca'
import { openAjustes } from './ajustes'
import { closeSessionChat, openSessionChat, openSessionId } from './session'
import { closeTerminal, openTerminal, openTerminalId } from './terminales'
import { piezas } from '../piezas'

export const paleta = ref(false)
export const recientes = ref<string[]>(loadRecientes())

function piezasCatalogo(): PiezasCatalogo {
  const ps = piezas()
  return {
    secciones: ps.flatMap((p) => (p.buscador?.seccion ? [{ s: p.id, ...p.buscador.seccion }] : [])),
    acciones: ps.flatMap((p) => p.buscador?.acciones ?? []),
    avisos: ps.flatMap((p) => (p.avisos ? [p.avisos] : [])),
  }
}

export const catalogo = computed<Entrada[]>(() =>
  construirCatalogo({ board: boardState.value.board, items: libItems.value, avisos: av.items, tema: theme.value, piezas: piezasCatalogo() }),
)

export function resultados(consulta: string): Seccionado[] {
  return consulta.trim() ? buscar(consulta, catalogo.value) : inicial(catalogo.value, recientes.value)
}
export const planos = (s: Seccionado[]) => aplanar(s)

export function abrirPaleta() {
  if (auth.value === 'ready') paleta.value = true
}
export const cerrarPaleta = () => (paleta.value = false)
export const alternarPaleta = () => (paleta.value ? cerrarPaleta() : abrirPaleta())

function liberarPantalla() {
  if (openSessionId.value && !desktop.value) closeSessionChat()
  if (openTerminalId.value && !desktop.value) closeTerminal()
}

function irASeccion(s: Seccion) {
  if (s === 'ajustes') return openAjustes()
  liberarPantalla()
  const seccionPieza = piezas().find((p) => p.id === s)?.seccion
  if (seccionPieza || s === 'biblioteca') {
    for (const p of piezas()) if (p.seccion && p.seccion !== seccionPieza) p.seccion.visible.value = false
    libVisible.value = s === 'biblioteca'
    if (seccionPieza) seccionPieza.visible.value = true
  } else if (s === 'board') {
    viewRequest.value = { view: 'board', n: Date.now() }
  }
}

export function ejecutar(d: Destino) {
  switch (d.t) {
    case 'seccion':
      return irASeccion(d.s)
    case 'accion':
      if (d.a === 'tema') return setTheme(theme.value === 'dark' ? 'light' : 'dark')
      return piezas().flatMap((p) => p.buscador?.acciones ?? []).find((a) => a.id === d.a)?.correr()
    case 'sesion':
      return openSessionChat(d.id)
    case 'terminal':
      return openTerminal(d.id)
    case 'pane':
      liberarPantalla()
      return showOnBoard(d.id)
    case 'biblioteca':
      return void (desktop.value ? openInLibrary(d.id) : openOverlay(d.id))
    case 'aviso': {
      const a = av.items.find((x) => x.id === d.id)
      if (a) irAAviso(a)
    }
  }
}

export function elegir(e: Entrada) {
  recientes.value = sumarReciente(recientes.value, e.id)
  saveRecientes(recientes.value)
  cerrarPaleta()
  ejecutar(e.destino)
}

watch(auth, (a) => a !== 'ready' && cerrarPaleta())

<script lang="ts">
import { superaUmbral } from '../lib/geometria'
import { observarFueraDeVista } from '../lib/fueraDeVista'

export { superaUmbral }

/** Cancela el long-press táctil de la manija de tarjeta si hubo movimiento antes de armar el arrastre. */
export function debeCancelarGripHoldPorMovimiento(
  x0: number,
  y0: number,
  x: number,
  y: number,
  arrastreArmado: boolean,
): boolean {
  if (arrastreArmado) return false
  return superaUmbral(x0, y0, x, y)
}

/** Cancela el long-press táctil de pestaña si hubo movimiento antes de armar el arrastre. */
export function debeCancelarPestHoldPorMovimiento(
  x0: number,
  y0: number,
  x: number,
  y: number,
  arrastreArmado: boolean,
): boolean {
  if (arrastreArmado) return false
  return superaUmbral(x0, y0, x, y)
}
</script>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Agent, Workspace } from '../api/types'
import { boardState } from '../state/app'
import {
  agentEsActivoParaOrden,
  aplicarOrdenPestanas,
  claveGrupoPestanas,
  idDePane,
  moverEnOrden,
  ordenTrasArrastreQuietos,
  wsFlags,
} from '../lib/order'
import { guardarOrdenPestanas, ordenPestanasGuardado } from '../state/ordenTablero'
import AgentRow from './AgentRow.vue'
import TabLine from './TabLine.vue'
import TerminalGroup from './TerminalGroup.vue'
import Icon from './Icon.vue'
import StatusPill from './StatusPill.vue'
import { openClose } from '../state/cerrar'
import { protectedTabClosable } from '../lib/cerrar'
import { openSessionId } from '../state/session'
import { renombrarTerminal } from '../state/app'
import { armarRenombrar, createLongPress, grupoRenombrable, NOMBRE_MAX, pestanaActiva, pestanaRenombrable } from '../lib/renombrar'
import type { TipoRenombrar } from '../lib/renombrar'
import { desktop } from '../lib/viewport'
import type { Tab } from '../api/types'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { ocultarNombreTab, tituloTarjeta } from '../lib/cardTitle'

export interface ReorderUi {
  index: number
  total: number
  canUp?: boolean
  canDown?: boolean
  dropBefore?: boolean
  lifting?: boolean
  arming?: boolean
}

export interface PestanaReorderUi {
  index: number
  total: number
  dropBefore?: boolean
  lifting?: boolean
}

const props = defineProps<{
  ws: Workspace
  now: number
  reorder?: ReorderUi | null
  plegada?: boolean
  plegadasErr?: string
}>()
const emit = defineEmits<{
  'reorder-key': [delta: -1 | 1]
  'reorder-move': [delta: -1 | 1]
  'grip-down': [e: PointerEvent]
  'grip-cancel-hold': []
  'toggle-plegada': []
  'sumar-pestana': []
}>()

const transitions = computed(() => boardState.value.transitions)
const flags = computed(() => wsFlags(props.ws))
const pill = computed<{ status: 'blocked' | 'working' | 'fondo'; label?: string } | null>(() => {
  const f = flags.value
  if (f.blocked) return { status: 'blocked' }
  if (f.asks) return { status: 'blocked', label: 'Te pregunta' }
  if (f.working) return { status: 'working' }
  if (f.fondo) return { status: 'fondo' }
  return null
})
const rail = computed(() => (pill.value ? pill.value.status : 'calm'))
const soloAgent = computed(() => props.ws.tabs.reduce((n, t) => n + t.agents.length, 0) === 1)
const { run } = useGsap()
const railEl = ref<HTMLElement | null>(null)
watch(rail, (r, o) => {
  if (r === o || r === 'calm' || !railEl.value) return
  if (isSoft()) return
  run(() =>
    gsap.fromTo(
      railEl.value,
      { scaleY: 0.2, filter: 'brightness(2)' },
      { scaleY: 1, filter: 'brightness(1)', duration: 0.35, ease: 'power3.out' },
    ),
  )
})
const tabLabel = (label: string, i: number) => (label && !/^\d+$/.test(label) ? label : `tab ${label || i + 1}`)
const tituloAgente = (ag: Tab['agents'][number], tab: Tab, i: number) =>
  tituloTarjeta(ag.title, ag.doing, tab.label)
const ocultarTab = (tab: Tab, i: number) => {
  if (tab.agents.length !== 1) return false
  const ag = tab.agents[0]!
  return ocultarNombreTab(1, tabLabel(tab.label, i), tituloAgente(ag, tab, i))
}
const tabHere = (tab: Tab) => desktop.value && !!openSessionId.value && tab.agents.some((a) => a.session_id === openSessionId.value)

function agentsEnTab(tab: Tab): Agent[] {
  const clave = claveGrupoPestanas(props.ws.id, tab.id)
  const orden = ordenPestanasGuardado.value[clave] ?? []
  return aplicarOrdenPestanas(tab.agents, orden)
}

const wsView = computed(() => ({
  ...props.ws,
  tabs: props.ws.tabs.map((t) => ({ ...t, agents: agentsEnTab(t) })),
}))

const pestCountLabel = computed(() => {
  const n = props.ws.tabs.length
  return `${n} ${n === 1 ? 'pestaña' : 'pestañas'}`
})

let cuerpoTween: gsap.core.Tween | null = null
const wsBodyEl = ref<HTMLElement | null>(null)
const omitirAnimPlegado = ref(!!props.plegada)

function onCuerpoEnter(el: Element, done: () => void) {
  const e = el as HTMLElement
  if (omitirAnimPlegado.value || isSoft()) {
    omitirAnimPlegado.value = false
    gsap.set(e, { clearProps: 'height,opacity,overflow' })
    done()
    return
  }
  cuerpoTween?.kill()
  gsap.set(e, { height: 0, opacity: 0, overflow: 'hidden' })
  run(() => {
    cuerpoTween = gsap.to(e, {
      height: 'auto',
      opacity: 1,
      duration: 0.28,
      ease: 'power2.out',
      onComplete: () => {
        gsap.set(e, { clearProps: 'height,opacity,overflow' })
        cuerpoTween = null
        done()
      },
    })
  })
}

function onCuerpoLeave(el: Element, done: () => void) {
  const e = el as HTMLElement
  if (isSoft()) {
    done()
    return
  }
  cuerpoTween?.kill()
  const h = e.offsetHeight
  gsap.set(e, { height: h, overflow: 'hidden' })
  run(() => {
    cuerpoTween = gsap.to(e, {
      height: 0,
      opacity: 0,
      duration: 0.28,
      ease: 'power2.out',
      onComplete: () => {
        gsap.set(e, { clearProps: 'height,opacity,overflow' })
        cuerpoTween = null
        done()
      },
    })
  })
}

watch(
  () => props.plegada,
  (folded, was) => {
    if (folded === was) return
    cuerpoTween?.kill()
    cuerpoTween = null
    if (wsBodyEl.value) gsap.set(wsBodyEl.value, { clearProps: 'height,opacity,overflow' })
  },
)

const dragTabId = ref<string | null>(null)
const dragFrom = ref<number | null>(null)
const dragOver = ref<number | null>(null)
const pestArmed = ref(false)
const ROOT_DRAG_PEST = 'orq-arrastrando-pestana'
const PEST_GRIP_MS = 360
let pestHold: ReturnType<typeof setTimeout> | undefined
let pestGripX = 0
let pestGripY = 0
let pestStart: { tabId: string; index: number; id: number; el: HTMLElement } | null = null
let pestListeners: (() => void) | null = null

function detachPestDrag() {
  pestListeners?.()
  pestListeners = null
  document.documentElement.classList.remove(ROOT_DRAG_PEST)
  pestStart = null
  pestArmed.value = false
  dragTabId.value = null
  dragFrom.value = null
  dragOver.value = null
}

function pestanaEsActiva(ag: Agent): boolean {
  return agentEsActivoParaOrden(ag)
}

function pestanaRows(tabId: string) {
  return [...(document.querySelectorAll<HTMLElement>(`[data-pest-tab="${tabId}"] .pestana-row`) ?? [])]
}

function indexPestanaAtY(tabId: string, y: number): number {
  const els = pestanaRows(tabId)
  if (!els.length) return 0
  for (let i = 0; i < els.length; i++) {
    const r = els[i]!.getBoundingClientRect()
    if (y < r.top + r.height / 2) return i
  }
  return els.length - 1
}

function manualPestanaIds(tab: Tab): string[] {
  return agentsEnTab(tab).map(idDePane)
}

function commitPestanaOrder(tab: Tab, ids: string[]) {
  void guardarOrdenPestanas(claveGrupoPestanas(props.ws.id, tab.id), ids)
}

function movePestana(tab: Tab, from: number, to: number) {
  if (from === to) return
  const clave = claveGrupoPestanas(props.ws.id, tab.id)
  const visual = moverEnOrden(manualPestanaIds(tab), from, to)
  const esActivo = (id: string) => {
    const ag = tab.agents.find((a) => a.pane_id === id)
    return ag ? pestanaEsActiva(ag) : false
  }
  commitPestanaOrder(tab, ordenTrasArrastreQuietos(visual, esActivo, ordenPestanasGuardado.value[clave] ?? []))
}

function pestanaReorderUi(tab: Tab, index: number): PestanaReorderUi {
  const total = tab.agents.length
  const active = dragTabId.value === tab.id
  return {
    index,
    total,
    dropBefore: active && dragOver.value === index && dragFrom.value !== null && dragFrom.value !== index,
    lifting: active && dragFrom.value === index,
  }
}

function onPestanaReorderKey(tab: Tab, index: number, delta: -1 | 1) {
  const to = index + delta
  if (to < 0 || to >= tab.agents.length) return
  movePestana(tab, index, to)
}

function onPestGripCancelHold() {
  if (pestArmed.value) return
  clearTimeout(pestHold)
}

function onPestGripMove(e: PointerEvent) {
  if (debeCancelarPestHoldPorMovimiento(pestGripX, pestGripY, e.clientX, e.clientY, pestArmed.value)) {
    clearTimeout(pestHold)
  }
}

function onPestTouchStart(e: TouchEvent) {
  if (e.cancelable) e.preventDefault()
}
function onPestTouchMove(e: TouchEvent) {
  if (e.cancelable) e.preventDefault()
}
function onPestGripDown(tab: Tab, index: number, e: PointerEvent) {
  if (e.button !== 0 || tab.agents.length < 2) return
  const ag = tab.agents[index]
  if (ag && pestanaEsActiva(ag)) return
  const el = e.currentTarget as HTMLElement
  if (e.pointerType === 'touch') e.preventDefault()
  const arm = () => {
    pestArmed.value = true
    haptic(8)
    e.preventDefault()
    pestStart = { tabId: tab.id, index, id: e.pointerId, el }
    dragTabId.value = tab.id
    dragFrom.value = index
    dragOver.value = index
    document.documentElement.classList.add(ROOT_DRAG_PEST)
    try {
      el.setPointerCapture(e.pointerId)
    } catch {
      /* captura perdida */
    }
    const move = (ev: PointerEvent) => {
      if (ev.pointerId !== pestStart?.id) return
      if (ev.cancelable) ev.preventDefault()
      dragOver.value = indexPestanaAtY(tab.id, ev.clientY)
    }
    const end = (ev: PointerEvent) => {
      if (ev.pointerId !== pestStart?.id) return
      const from = dragFrom.value
      const to = dragOver.value
      if (el.hasPointerCapture(ev.pointerId)) el.releasePointerCapture(ev.pointerId)
      detachPestDrag()
      if (from !== null && to !== null) movePestana(tab, from, to)
    }
    const cancel = (ev: PointerEvent) => {
      if (ev.pointerId !== pestStart?.id || !pestArmed.value) return
      end(ev)
    }
    const opts = { capture: true }
    window.addEventListener('pointermove', move, opts)
    window.addEventListener('pointerup', end, opts)
    window.addEventListener('pointercancel', cancel, opts)
    pestListeners = () => {
      window.removeEventListener('pointermove', move, opts)
      window.removeEventListener('pointerup', end, opts)
      window.removeEventListener('pointercancel', cancel, opts)
    }
  }
  pestArmed.value = false
  if (e.pointerType === 'touch') {
    pestGripX = e.clientX
    pestGripY = e.clientY
    clearTimeout(pestHold)
    pestHold = setTimeout(arm, PEST_GRIP_MS)
    return
  }
  arm()
}

const wsName = computed(() => props.ws.label || `Workspace ${props.ws.number}`)
const menu = ref(false)
const menuEl = ref<HTMLElement | null>(null)
let hold: ReturnType<typeof setTimeout> | undefined
let held = false
const cancelHold = () => clearTimeout(hold)
function pressStart(e: PointerEvent) {
  if (props.ws.pinned) return
  const t = e.target as HTMLElement
  if (t.closest('.ws-grip, .pest-grip, .ws-fold, .ws-title-btn, .tab-head, .rename-input')) return
  if (e.pointerType !== 'touch' || t.closest('button, a, [role=button]')) return
  held = false
  hold = setTimeout(() => {
    held = true
    haptic(14)
    menu.value = true
  }, 550)
}
const puedeRenombrarGrupo = computed(() => grupoRenombrable(props.ws))
const editando = ref<{ tipo: TipoRenombrar; id: string; actual: string } | null>(null)
const borrador = ref('')
const renombrarErr = ref('')
let inputEl: HTMLInputElement | null = null
let editCerrada = false
const setInput = (el: unknown) => {
  inputEl = el as HTMLInputElement | null
}
function empezarRenombrar(tipo: TipoRenombrar, id: string, actual: string) {
  menu.value = false
  renombrarErr.value = ''
  editCerrada = false
  editando.value = { tipo, id, actual }
  borrador.value = actual
  void nextTick(() => {
    inputEl?.focus()
    inputEl?.select()
  })
}
function renombrarGrupo() {
  if (!puedeRenombrarGrupo.value) return
  empezarRenombrar('grupo', props.ws.id, props.ws.label)
}
function renombrarPestana(tab: Tab, i: number) {
  if (!pestanaRenombrable(props.ws, tab)) return
  empezarRenombrar('pestana', tab.id, tab.label && !/^\d+$/.test(tab.label) ? tab.label : tabLabel(tab.label, i))
}
function renombrarPestanaActiva() {
  const tabs = props.ws.tabs
  const abierta = tabs.find((t) => tabHere(t))?.id ?? null
  const tab = pestanaActiva(tabs, abierta, boardState.value.board?.focused_tab_id ?? null)
  if (tab) renombrarPestana(tab, tabs.indexOf(tab))
}
function cancelarRenombrar() {
  if (editCerrada) return
  editCerrada = true
  editando.value = null
}
async function guardarRenombrar() {
  const e = editando.value
  if (!e || editCerrada) return
  editCerrada = true
  const body = armarRenombrar(e.tipo, e.id, borrador.value, e.actual)
  editando.value = null
  if (!body) return
  try {
    await renombrarTerminal(body)
  } catch (err) {
    renombrarErr.value = err instanceof Error && err.message ? err.message : 'No pude cambiar el nombre'
  }
}
function onRenombrarKey(ev: KeyboardEvent) {
  if (ev.key === 'Enter') {
    ev.preventDefault()
    void guardarRenombrar()
  } else if (ev.key === 'Escape') {
    ev.preventDefault()
    ev.stopPropagation()
    cancelarRenombrar()
  }
}
let pestPress: ReturnType<typeof createLongPress> | null = null
function onTabHeadDown(tab: Tab, i: number, e: PointerEvent) {
  if (e.button !== 0 || !pestanaRenombrable(props.ws, tab)) return
  if ((e.target as HTMLElement).closest('button, input')) return
  pestPress?.cancel()
  pestPress = createLongPress(() => {
    haptic(10)
    renombrarPestana(tab, i)
  })
  pestPress.down(e.clientX, e.clientY)
}
const onTabHeadMove = (e: PointerEvent) => pestPress?.move(e.clientX, e.clientY)
const onTabHeadEnd = () => pestPress?.cancel()
function onTabHeadContext(tab: Tab, i: number, e: MouseEvent) {
  if (!pestanaRenombrable(props.ws, tab)) return
  if ((e.target as HTMLElement).closest('button, input')) return
  e.preventDefault()
  pestPress?.cancel()
  renombrarPestana(tab, i)
}
function sumarPestana() {
  menu.value = false
  emit('sumar-pestana')
}
function closeWorkspace() {
  menu.value = false
  openClose({
    tipo: 'workspace',
    targetId: props.ws.id,
    label: wsName.value,
    tabCount: props.ws.tabs.length,
    origen: 'manual',
    destino: wsName.value,
    porQue: '',
  })
}
function closeTab(tab: Tab, i: number) {
  const name = tabLabel(tab.label, i)
  openClose({
    tipo: 'tab',
    targetId: tab.id,
    label: name,
    tabCount: 1,
    origen: 'manual',
    destino: `${wsName.value} / ${name}`,
    porQue: '',
  })
}
function outside(e: Event) {
  if (menuEl.value && !menuEl.value.contains(e.target as Node)) menu.value = false
}
function onEsc(e: Event) {
  if ((e as KeyboardEvent).key === 'Escape') menu.value = false
}

function onGripKey(e: KeyboardEvent) {
  if (!props.reorder) return
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    emit('reorder-key', -1)
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    emit('reorder-key', 1)
  }
}

function onMenuReorder(delta: -1 | 1) {
  if (!props.reorder) return
  if (delta === -1 && props.reorder.canUp === false) return
  if (delta === 1 && props.reorder.canDown === false) return
  emit('reorder-move', delta)
}
let gripX = 0
let gripY = 0
function onGripTouchStart(e: TouchEvent) {
  if (e.cancelable) e.preventDefault()
}
function onGripTouchMove(e: TouchEvent) {
  if (e.cancelable) e.preventDefault()
}
function onGripDown(e: PointerEvent) {
  if (e.button !== 0) return
  if (e.pointerType === 'touch') e.preventDefault()
  gripX = e.clientX
  gripY = e.clientY
  emit('grip-down', e)
}
function onGripMove(e: PointerEvent) {
  const armed = !!props.reorder?.arming || !!props.reorder?.lifting
  if (debeCancelarGripHoldPorMovimiento(gripX, gripY, e.clientX, e.clientY, armed)) emit('grip-cancel-hold')
}
function onGripEndCancel() {
  if (props.reorder?.arming || props.reorder?.lifting) return
  emit('grip-cancel-hold')
}
function togglePlegadaFromHead() {
  haptic(4)
  if (props.plegada) emit('toggle-plegada')
}
function onFoldClick() {
  haptic(4)
  emit('toggle-plegada')
}
watch(menu, (on) => {
  const f = on ? document.addEventListener : document.removeEventListener
  f.call(document, 'pointerdown', outside, true)
  f.call(document, 'keydown', onEsc)
})
const cardEl = ref<HTMLElement | null>(null)
let soltarVista = () => {}
onMounted(() => {
  if (cardEl.value) soltarVista = observarFueraDeVista(cardEl.value)
})
onBeforeUnmount(() => {
  soltarVista()
  cuerpoTween?.kill()
  cancelHold()
  pestPress?.cancel()
  clearTimeout(pestHold)
  detachPestDrag()
  document.removeEventListener('pointerdown', outside, true)
  document.removeEventListener('keydown', onEsc)
})

function onPestGripKey(tab: Tab, index: number, e: KeyboardEvent) {
  if (tab.agents.length < 2) return
  if (e.key === 'ArrowUp') {
    e.preventDefault()
    onPestanaReorderKey(tab, index, -1)
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    onPestanaReorderKey(tab, index, 1)
  }
}
</script>

<template>
  <article
    ref="cardEl"
    class="ws"
    :data-rail="rail"
    :class="{
      'menu-open': menu,
      'is-plegada': plegada,
      'drop-before': reorder?.dropBefore,
      lifting: reorder?.lifting,
      arming: reorder?.arming,
    }"
    @pointerdown="pressStart"
    @pointerup="cancelHold"
    @pointermove="cancelHold"
    @pointercancel="cancelHold"
    @contextmenu="held && $event.preventDefault()"
  >
    <i class="spot" aria-hidden="true" />
    <i class="lift" aria-hidden="true" />
    <i ref="railEl" class="rail loop" aria-hidden="true" />
    <div class="body">
      <header class="ws-head">
        <button
          v-if="reorder"
          type="button"
          class="ws-grip hit"
          aria-label="Mover tarjeta"
          @keydown="onGripKey"
          @contextmenu.prevent
          @pointerdown.stop="onGripDown"
          @pointerup.stop="onGripEndCancel"
          @pointercancel.stop="onGripEndCancel"
          @pointermove.stop="onGripMove"
          @touchstart.stop.prevent="onGripTouchStart"
          @touchmove.stop.prevent="onGripTouchMove"
        />
        <button
          type="button"
          class="ws-fold hit"
          :class="{ 'fold-ico-on': plegada }"
          :aria-expanded="!plegada"
          :aria-label="plegada ? 'Desplegar tarjeta' : 'Plegar tarjeta'"
          @click="onFoldClick"
        >
          <Icon name="chevron" :size="16" class="fold-ico" />
        </button>
        <i v-if="flags.unread" class="new-dot" title="Respuesta nueva" aria-label="Respuesta nueva" />
        <input
          v-if="editando?.tipo === 'grupo'"
          :ref="setInput"
          v-model="borrador"
          class="rename-input ws-rename"
          type="text"
          :maxlength="NOMBRE_MAX"
          aria-label="Nombre del grupo"
          enterkeyhint="done"
          @keydown="onRenombrarKey"
          @blur="cancelarRenombrar"
        />
        <button v-else type="button" class="ws-title-btn label" :aria-expanded="!plegada" @click="togglePlegadaFromHead">
          {{ wsView.label || `Workspace ${wsView.number}` }}
        </button>
        <StatusPill v-if="pill" :status="pill.status" :label="pill.label" />
        <Transition name="tab-count-fade">
          <span v-if="plegada" key="count" class="tab-count">
            <span class="tab-count-full">{{ pestCountLabel }}</span>
            <span class="tab-count-short">{{ ws.tabs.length }}</span>
          </span>
        </Transition>
        <div v-if="!ws.pinned" ref="menuEl" class="ws-menu">
          <button
            type="button"
            class="dots"
            :aria-expanded="menu"
            aria-haspopup="menu"
            :aria-label="`Más acciones de ${wsName}`"
            @click="menu = !menu"
          >
            <Icon name="dots" :size="16" />
          </button>
          <Transition name="pop">
            <div v-if="menu" class="pop" role="menu" @pointerdown.stop>
              <template v-if="reorder">
                <button
                  type="button"
                  role="menuitem"
                  class="item"
                  :class="{ off: reorder.canUp === false }"
                  :aria-disabled="reorder.canUp === false ? 'true' : undefined"
                  @click="onMenuReorder(-1)"
                >
                  <Icon name="arrow-up" :size="13" /> Subir
                </button>
                <button
                  type="button"
                  role="menuitem"
                  class="item"
                  :class="{ off: reorder.canDown === false }"
                  :aria-disabled="reorder.canDown === false ? 'true' : undefined"
                  @click="onMenuReorder(1)"
                >
                  <Icon name="down" :size="13" /> Bajar
                </button>
                <div class="pop-sep" role="separator" aria-hidden="true" />
              </template>
              <button v-if="puedeRenombrarGrupo" type="button" role="menuitem" class="item" @click="sumarPestana">
                <Icon name="plus" :size="13" /> Sumar pestaña
              </button>
              <button v-if="puedeRenombrarGrupo" type="button" role="menuitem" class="item" @click="renombrarGrupo">
                <Icon name="pen" :size="13" /> Renombrar grupo
              </button>
              <button v-if="puedeRenombrarGrupo && ws.tabs.length" type="button" role="menuitem" class="item" @click="renombrarPestanaActiva">
                <Icon name="pen" :size="13" /> Renombrar pestaña
              </button>
              <button type="button" role="menuitem" class="item danger" @click="closeWorkspace"><Icon name="close" :size="13" /> Cerrar workspace</button>
            </div>
          </Transition>
        </div>
        <p v-if="plegadasErr" class="fold-err" role="alert">{{ plegadasErr }}</p>
        <p v-if="renombrarErr" class="fold-err" role="alert">{{ renombrarErr }}</p>
      </header>

      <Transition :css="false" @enter="onCuerpoEnter" @leave="onCuerpoLeave">
        <div v-show="!plegada" ref="wsBodyEl" class="ws-body" :aria-hidden="plegada">
      <section
        v-for="(tab, i) in wsView.tabs"
        :key="tab.id"
        :data-pest-tab="tab.id"
        class="tab"
        :class="{ here: tabHere(tab) }"
      >
        <TabLine :on="tabHere(tab)" />
        <div
          class="tab-head"
          :class="{ compact: ocultarTab(tab, i) && editando?.id !== tab.id }"
          @pointerdown="onTabHeadDown(tab, i, $event)"
          @pointermove="onTabHeadMove"
          @pointerup="onTabHeadEnd"
          @pointercancel="onTabHeadEnd"
          @contextmenu="onTabHeadContext(tab, i, $event)"
        >
          <input
            v-if="editando?.id === tab.id"
            :ref="setInput"
            v-model="borrador"
            class="rename-input tab-rename"
            type="text"
            :maxlength="NOMBRE_MAX"
            aria-label="Nombre de la pestaña"
            enterkeyhint="done"
            @keydown="onRenombrarKey"
            @blur="cancelarRenombrar"
          />
          <span v-else-if="!ocultarTab(tab, i)" class="tab-name mono">{{ tabLabel(tab.label, i) }}</span>
          <button
            v-if="protectedTabClosable(ws, tab)"
            type="button"
            class="tab-close"
            :aria-label="`Cerrar ${tabLabel(tab.label, i)}`"
            title="Cerrar tab"
            @click="closeTab(tab, i)"
          >
            <Icon name="close" :size="13" />
          </button>
        </div>
        <div
          v-for="(ag, ai) in tab.agents"
          :key="ag.pane_id"
          class="pestana-row"
          :class="{
            'drop-before': pestanaReorderUi(tab, ai).dropBefore,
            lifting: pestanaReorderUi(tab, ai).lifting,
          }"
        >
          <button
            v-if="tab.agents.length > 1 && !pestanaEsActiva(ag)"
            type="button"
            class="pest-grip hit"
            aria-label="Mover pestaña"
            @keydown="onPestGripKey(tab, ai, $event)"
            @contextmenu.prevent
            @pointerdown.stop="onPestGripDown(tab, ai, $event)"
            @pointerup.stop="onPestGripCancelHold"
            @pointercancel.stop="onPestGripCancelHold"
            @pointermove.stop="onPestGripMove"
            @touchstart.stop.prevent="onPestTouchStart"
            @touchmove.stop.prevent="onPestTouchMove"
          />
          <AgentRow
            :agent="ag"
            :ws-label="wsView.label || `Workspace ${wsView.number}`"
            :now="now"
            :changed-from="transitions[ag.pane_id]"
            :hide-status="soloAgent"
            :tab-id="tab.id"
            :tab-label="tabLabel(tab.label, i)"
            :tab-label-raw="tab.label"
            :closable="!ws.pinned"
          />
        </div>
        <TerminalGroup v-if="tab.terminales?.length" :terminals="tab.terminales" :collapsible="tab.agents.length > 0" />
        <p v-else-if="!tab.agents.length" class="no-agent">Terminal sin agente</p>
      </section>
        </div>
      </Transition>
    </div>
  </article>
</template>

<style scoped>
.ws-grip {
  position: absolute;
  left: -10px;
  top: 50%;
  transform: translateY(-50%);
  z-index: 2;
  display: grid;
  place-items: center;
  width: 28px;
  height: 32px;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 8px;
  color: var(--text-3);
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  opacity: 0;
  transition: opacity 0.2s, background 0.2s, color 0.2s;
}
.ws.is-plegada .ws-grip {
  opacity: 0.72;
}
.ws-fold {
  display: grid;
  place-items: center;
  flex: none;
  width: 32px;
  height: 32px;
  margin: 0;
  padding: 0;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition: background 0.2s, color 0.2s, transform 0.25s var(--ease-out);
}
.ws-fold:focus-visible {
  color: var(--text-2);
  background: var(--surface-hover);
}
.fold-ico {
  transition: transform 0.28s var(--ease-out);
  transform: rotate(90deg);
}
.ws-fold.fold-ico-on .fold-ico {
  transform: rotate(0deg);
}
.tab-count-fade-enter-active,
.tab-count-fade-leave-active {
  transition: opacity 0.22s var(--ease-out);
}
.tab-count-fade-enter-from,
.tab-count-fade-leave-to {
  opacity: 0;
}
.ws-title-btn {
  flex: 1;
  min-width: 0;
  margin: 0;
  padding: 0;
  border: none;
  background: none;
  text-align: left;
  cursor: pointer;
  font: inherit;
  color: inherit;
  white-space: nowrap;
}
.ws-title-btn.label {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tab-count {
  flex: none;
  font-size: 11px;
  color: var(--text-3);
  white-space: nowrap;
}
.tab-count-short {
  display: none;
}
.fold-err {
  flex: 1 1 100%;
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--danger);
}
.ws.arming {
  transform: scale(0.992);
  opacity: 0.88;
}
@media (pointer: coarse) {
  .ws-grip,
  .pest-grip {
    display: none !important;
  }
}
.ws-grip::before {
  content: '';
  width: 10px;
  height: 16px;
  background: radial-gradient(circle at 50% 50%, currentColor 1.25px, transparent 1.4px);
  background-size: 10px 5px;
}
.ws:hover .ws-grip,
.ws.menu-open .ws-grip,
.ws.lifting .ws-grip,
.ws-grip:focus-visible {
  opacity: 1;
}
.ws-grip:hover,
.ws-grip:focus-visible {
  color: var(--text-2);
  background: var(--surface-hover);
}
@media (hover: none) {
  .ws-grip {
    opacity: 0.72;
  }
}
.ws.drop-before::after {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  top: -1px;
  height: 3px;
  border-radius: var(--r-pill);
  background: color-mix(in srgb, var(--accent) 75%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
  pointer-events: none;
  z-index: 3;
}
.ws.lifting:not(.drag-float) {
  opacity: 0.62;
  transform: scale(0.992);
  z-index: 2;
}
.ws.drag-float {
  position: relative;
  z-index: 6;
  opacity: 1;
  background: var(--surface);
  box-shadow: 0 18px 40px -16px rgb(0 0 0 / 0.55), 0 0 0 1px var(--line);
  will-change: transform;
}
.ws-menu {
  position: relative;
  margin-left: auto;
}
.dots {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  color: var(--text-3);
  opacity: 0;
  transition: opacity 0.2s, background 0.2s, color 0.2s;
}
.ws:hover .dots,
.ws.menu-open .dots,
.dots:focus-visible {
  opacity: 1;
}
@media (hover: none) {
  .dots { opacity: 0.55; }
}
@media (hover: hover) {
  .ws-menu { transition: margin 0.25s var(--ease-out); }
  .dots { transition: opacity 0.2s, background 0.2s, color 0.2s, width 0.25s var(--ease-out); }
  .ws:not(:hover):not(.menu-open):not(:focus-within) .ws-menu { margin-left: -10px; }
  .ws:not(:hover):not(.menu-open):not(:focus-within) .dots { width: 0; }
}
.tab-close {
  display: grid;
  place-items: center;
  flex: none;
  width: 28px;
  height: 28px;
  margin-left: auto;
  border-radius: 50%;
  color: var(--text-3);
  opacity: 0;
  transition: opacity 0.2s, background 0.2s, color 0.2s;
}
.tab:hover .tab-close,
.tab-close:focus-visible {
  opacity: 1;
}
@media (hover: none) {
  .tab-close { opacity: 0.55; width: 36px; height: 36px; margin-right: -4px; }
}
.tab-close:hover {
  color: var(--danger);
  background: var(--danger-soft);
}
.pop {
  position: absolute;
  right: 0;
  top: calc(100% + 4px);
  z-index: 8;
  min-width: 190px;
  padding: 4px;
  border-radius: 12px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  box-shadow: var(--shadow-pop);
  transform-origin: 100% 0;
}
.item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 13px;
  text-align: left;
  color: var(--text);
}
.item.off,
.item[aria-disabled='true'] {
  opacity: 0.42;
  cursor: default;
  pointer-events: none;
}
.item.danger { color: var(--danger); }
.pop-sep {
  height: 1px;
  margin: 4px 8px;
  background: var(--line);
}
@media (hover: hover) {
  .ws-fold:hover {
    color: var(--text-2);
    background: var(--surface-hover);
  }
  .dots:hover {
    color: var(--text);
    background: var(--surface-hover);
  }
  .item:not(.danger):not(.off):hover {
    background: var(--surface-hover);
  }
  .item.danger:hover {
    background: var(--danger-soft);
  }
}
.pop-enter-active { transition: opacity 0.18s, transform 0.35s var(--spring); }
.pop-leave-active { transition: opacity 0.12s; }
.pop-enter-from { opacity: 0; transform: scale(0.92) translateY(-4px); }
.pop-leave-to { opacity: 0; }

.ws {
  --c: transparent;
  position: relative;
  min-width: 0;
  max-width: 100%;
  padding: 16px 12px 16px 16px;
  border-radius: var(--r-lg);
  transition: background 0.35s var(--ease-out), box-shadow 0.35s var(--ease-out);
}
.ws.is-plegada {
  box-shadow: inset 0 -1px 0 var(--line);
}
.ws.is-plegada .rail {
  bottom: 14px;
}
.ws.is-plegada .ws-head {
  padding-bottom: 0;
}
.ws.flying {
  z-index: 3;
  background: var(--surface);
  box-shadow: 0 18px 40px -16px rgb(0 0 0 / 0.55), 0 0 0 1px var(--line);
}
.ws[data-rail='working'] { --c: var(--st-working); }
.ws[data-rail='fondo'] { --c: var(--st-fondo); }
.ws[data-rail='blocked'] { --c: var(--st-blocked); }

.rail {
  position: absolute;
  left: 4px;
  top: 18px;
  bottom: 6px;
  width: 3px;
  border-radius: 3px;
  background: var(--c);
  opacity: 0;
  transform-origin: 50% 50%;
  transition: opacity 0.4s, background 0.4s;
}
.ws:not([data-rail='calm']) .rail { opacity: 0.9; }
.ws[data-rail='blocked'] .rail {
  box-shadow: 0 0 6px var(--c);
  animation: rail-call 2.8s var(--ease-in-out) infinite;
}
.ws[data-rail='blocked'] .rail::after {
  content: '';
  position: absolute;
  inset: 0;
  border-radius: inherit;
  box-shadow: 0 0 16px 1px var(--c);
  opacity: 0;
  pointer-events: none;
  animation: rail-call-glow 2.8s var(--ease-in-out) infinite;
}
.ws[data-rail='working'] .rail {
  opacity: 0.7;
}
@keyframes rail-call {
  0%, 100% { opacity: 0.75; }
  50% { opacity: 1; }
}
@keyframes rail-call-glow {
  50% { opacity: 1; }
}
.spot,
.lift {
  position: absolute;
  inset: 2px;
  border-radius: var(--r-lg);
  pointer-events: none;
}
.spot {
  opacity: 0;
  background: radial-gradient(360px circle at var(--mx, 50%) var(--my, 50%), color-mix(in srgb, var(--accent) 7%, transparent), transparent 60%);
  transition: opacity 0.35s var(--ease-out);
}
.ws[data-spot] .spot { opacity: 1; }
.lift {
  opacity: var(--lift, 0);
  background: linear-gradient(90deg, color-mix(in srgb, var(--c) 14%, transparent), transparent 70%);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 30%, transparent);
}
.body {
  position: relative;
}

.ws::after {
  content: '';
  position: absolute;
  left: 16px;
  right: 14px;
  bottom: 0;
  height: 1px;
  background: var(--line);
}

.body {
  min-width: 0;
}
.ws-head {
  position: relative;
  display: flex;
  align-items: center;
  gap: 10px;
  min-height: 32px;
  padding: 0 4px 6px 12px;
}
.pestana-row {
  position: relative;
}
.pestana-row.drop-before::before {
  content: '';
  position: absolute;
  left: 8px;
  right: 8px;
  top: -1px;
  height: 3px;
  border-radius: var(--r-pill);
  background: color-mix(in srgb, var(--accent) 75%, transparent);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 35%, transparent);
  pointer-events: none;
  z-index: 3;
}
.pestana-row.lifting {
  opacity: 0.62;
}
.pest-grip {
  position: absolute;
  left: -6px;
  top: 14px;
  z-index: 2;
  display: grid;
  place-items: center;
  width: 24px;
  height: 28px;
  margin: 0;
  padding: 0;
  border: none;
  background: transparent;
  border-radius: 6px;
  color: var(--text-3);
  cursor: grab;
  touch-action: none;
  user-select: none;
  -webkit-user-select: none;
  -webkit-touch-callout: none;
  opacity: 0;
  transition: opacity 0.2s, background 0.2s, color 0.2s;
}
.pest-grip::before {
  content: '';
  width: 8px;
  height: 14px;
  background: radial-gradient(circle at 50% 50%, currentColor 1px, transparent 1.2px);
  background-size: 8px 4px;
}
.tab:hover .pest-grip,
.pestana-row.lifting .pest-grip,
.pest-grip:focus-visible {
  opacity: 1;
}
.pest-grip:hover,
.pest-grip:focus-visible {
  color: var(--text-2);
  background: var(--surface-hover);
}
@media (hover: none) {
  .pest-grip {
    opacity: 0.72;
    width: 40px;
    height: 40px;
    left: -8px;
    top: 8px;
  }
}
:root.orq-arrastrando-pestana .scroll,
:root.orq-arrastrando-pestana .body {
  touch-action: none;
}
.new-dot {
  flex: none;
  width: 8px;
  height: 8px;
  margin: 0 -2px 0 0;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 10px var(--accent);
}
.label {
  min-width: 0;
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 17.5px;
  line-height: 1.2;
  letter-spacing: -0.02em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tab {
  position: relative;
  margin-top: 4px;
  border-radius: var(--r-md);
  transition: background 0.4s var(--ease-out), box-shadow 0.4s var(--ease-out);
}
.tab::before {
  content: '';
  position: absolute;
  left: 0;
  top: 10px;
  bottom: 10px;
  width: 2px;
  border-radius: 2px;
  background: var(--line-2);
  transition: background 0.4s, top 0.4s var(--ease-out), bottom 0.4s var(--ease-out), box-shadow 0.4s;
}
.tab-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 6px 0 12px;
  min-height: 30px;
}
.tab-head.compact {
  min-height: 0;
  padding-top: 2px;
  justify-content: flex-end;
}
.rename-input {
  flex: 1;
  min-width: 0;
  min-height: 44px;
  box-sizing: border-box;
  margin: 0;
  padding: 0 10px;
  font: inherit;
  font-size: 16px;
  color: var(--text);
  background: var(--surface-hover);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  outline: none;
}
.rename-input:focus-visible {
  border-color: var(--accent-line);
}
.tab-name {
  -webkit-touch-callout: none;
  user-select: none;
  -webkit-user-select: none;
  font-size: var(--t-xs);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-3);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
.no-agent {
  margin: 2px 0 8px;
  padding: 0 12px;
  font-size: var(--t-md);
  color: var(--text-4);
  font-style: italic;
}

@media (max-width: 640px) {
  .tab-count-full {
    display: none;
  }
  .tab-count-short {
    display: inline;
    min-width: 1.25rem;
    text-align: center;
    font-variant-numeric: tabular-nums;
  }
}
</style>

<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, onMounted, ref, watch } from 'vue'
import type { Agent, AgentStatus } from '../api/types'
import { enSegundoPlano, estadoEfectivo, masFondo, mostrarMeta, rotuloTarea } from '../lib/fondo'
import { rotuloTraba } from '../lib/trabas'
import { ago } from '../lib/time'
import { plainPreview } from '../lib/preview'
import { lineasEstado } from '../lib/estado'
import { tituloTarjeta } from '../lib/cardTitle'
import { highlight, loadDigest, marcarPreguntaVista } from '../state/app'
import { cargarSessionPreview } from '../lib/precarga'
import Icon from './Icon.vue'
import EstadoLineas from './EstadoLineas.vue'
import { openClose } from '../state/cerrar'
import { openSessionChat, openSessionId } from '../state/session'
import { desktop } from '../lib/viewport'
import StatusPill from './StatusPill.vue'
import MrPipe from './MrPipe.vue'
import { irAMr, mrDeSesion } from '../state/mrs'
import CtxRing from './CtxRing.vue'
import { ctxLine } from '../lib/contexto'
import { usoHoyLine } from '../lib/usoClaude'
import { esSesionTerminal, esTerminalPropia } from '../lib/terminalPropia'
import { abrirMudanza, puedeMudar } from '../state/mudanza'
import { silenciadasGuardado, silencioError, silenciarSesion } from '../state/ordenTablero'
import { irAPcAviso, irAPcEnviando, irAPcSesion } from '../state/irAPc'
import { abrirVivo, loadTerminalConfig, vivoHabilitado } from '../state/terminalVivo'
import { tconfig } from '../state/terminalActions'
import { burst, gsap, haptic, isSoft, ring, useGsap } from '../motion'

const SessionPreview = defineAsyncComponent(cargarSessionPreview)

const props = withDefaults(
  defineProps<{
    agent: Agent
    wsLabel: string
    now: number
    changedFrom?: AgentStatus
    hideStatus?: boolean
    tabId?: string
    tabLabel?: string
    tabLabelRaw?: string
    closable?: boolean
  }>(),
  { closable: true },
)
const open = ref(false)
const opened = ref(false)

const title = computed(() =>
  tituloTarjeta(props.agent.title, props.agent.doing, props.tabLabelRaw ?? ''),
)
const doing = computed(() => plainPreview(props.agent.doing))
const pending = computed(() => plainPreview(props.agent.pending))
const estado = computed(() => (props.agent.estado && lineasEstado(props.agent.estado).length ? props.agent.estado : null))
const showDoing = computed(() => !!doing.value && doing.value !== title.value)
const efectivo = computed(() => estadoEfectivo(props.agent))
const showPill = computed(() => !props.hideStatus && (props.agent.status !== 'idle' || enSegundoPlano(props.agent)))
const fondoLinea = computed(() => {
  const t = props.agent.fondo?.[0]
  if (!t) return ''
  const extra = masFondo(props.agent.fondo?.length ?? 0)
  return extra ? `${rotuloTarea(t)} ${extra}` : rotuloTarea(t)
})
const trabaRotulo = computed(() => (props.agent.traba ? rotuloTraba(props.agent.traba, props.now) : ''))
const meta = computed(() => mostrarMeta({
  traba: !!props.agent.traba,
  unread: !!props.agent.unread, pide: !!props.agent.asks_user || !!props.agent.pendiente, pill: showPill.value, doing: resumenEnCabecera.value && showDoing.value, mr: !!mr.value,
  otroKind: !!props.agent.kind && props.agent.kind !== 'claude', fondo: resumenEnCabecera.value && !!fondoLinea.value,
}))
const when = computed(() => ago(props.agent.last_activity, props.now))
const ctxText = computed(() => (props.agent.ctx ? ctxLine(props.agent.ctx, props.now) : ''))
const usoText = computed(() => usoHoyLine(props.agent.uso))
const canOpen = computed(() => !!props.agent.session_id)
// Contraída solo se ven título, píldoras, tiempo y ctx; el resumen vive en el cajón.
// Sin session_id no hay cajón que abrir, así que el resumen se queda en la cabecera.
const resumenEnCabecera = computed(() => !canOpen.value)
const resumenEnCajon = computed(() => canOpen.value && opened.value)
const mr = computed(() => mrDeSesion(props.agent.session_id))
const selected = computed(() => desktop.value && !!props.agent.session_id && openSessionId.value === props.agent.session_id)
const lit = computed(() => highlight.value?.paneId === props.agent.pane_id)

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const flash = ref<HTMLElement | null>(null)
const glow = ref<HTMLElement | null>(null)
const chip = ref<HTMLElement | null>(null)

function toggle() {
  if (!canOpen.value) return
  open.value = !open.value
  if (open.value && opened.value && props.agent.session_id) void loadDigest(props.agent.session_id)
  opened.value = true
}

function closeTab() {
  if (!props.tabId || !props.closable) return
  openClose({
    tipo: 'tab',
    targetId: props.tabId,
    label: props.tabLabel || title.value,
    tabCount: 1,
    origen: 'manual',
    destino: `${props.wsLabel} / ${props.tabLabel || title.value}`,
    porQue: '',
  })
}

function openChat() {
  if (props.agent.session_id) openSessionChat(props.agent.session_id)
}

onMounted(() => {
  if (!tconfig.value) void loadTerminalConfig()
})

const visible = (el: HTMLElement) => {
  const r = el.getBoundingClientRect()
  return r.width > 0 && r.bottom > 0 && r.top < innerHeight && r.left < innerWidth && r.right > 0
}
const needsYou = (st: string, asks: boolean) => st === 'blocked' || asks

watch(
  () => [props.agent.status, props.agent.asks_user] as const,
  ([st, asks], [pst, pasks]) => {
    if (st === pst && asks === pasks) return
    const el = root.value
    if (!el || !flash.value) return
    const resolved = needsYou(pst, pasks) && !needsYou(st, asks)
    if (isSoft()) {
      run(() => gsap.fromTo(flash.value, { opacity: 0.8 }, { opacity: 0, duration: 0.6 }))
      return
    }
    run(() => {
      const tl = gsap.timeline()
      tl.fromTo(flash.value, { opacity: 0, scaleX: 0.15 }, { opacity: 1, scaleX: 1, duration: 0.45, ease: 'expo.out' })
        .to(flash.value, { opacity: 0, duration: 1.4, ease: 'power2.out' }, 0.5)
      const pill = el.querySelector('.meta .pill')
      if (pill) tl.fromTo(pill, { scale: 0.7 }, { scale: 1, duration: 0.7, ease: 'elastic.out(1.2, 0.4)' }, 0.05)
      if (needsYou(st, asks) && !needsYou(pst, pasks)) {
        tl.fromTo(el, { x: 0 }, { keyframes: { x: [0, -4, 4, -2, 0] }, duration: 0.4, ease: 'none' }, 0.1)
      }
    })
    if (resolved && visible(el)) {
      const at = el.querySelector('.meta .pill') ?? el.querySelector('.title') ?? el
      const s = getComputedStyle(el)
      burst(at, { count: 16, power: 0.7, colors: [s.getPropertyValue('--accent'), s.getPropertyValue('--st-done'), s.getPropertyValue('--c')] })
      ring(at, s.getPropertyValue('--st-done'), 48)
      haptic(12)
    }
  },
)

watch(
  () => props.agent.unread,
  async (on, was) => {
    if (!on || was === undefined || isSoft()) return
    await nextTick()
    const el = chip.value
    if (!el) return
    run(() => gsap.fromTo(el, { scale: 0.6, opacity: 0 }, { scale: 1, opacity: 1, duration: 0.8, ease: 'elastic.out(1.1, 0.45)' }))
    ring(el, getComputedStyle(el).color, 40)
  },
)

watch(lit, (on) => {
  if (!on || !glow.value) return
  const el = glow.value
  setTimeout(() => {
    if (!lit.value) return
    if (isSoft()) {
      run(() => gsap.fromTo(el, { opacity: 0.5 }, { opacity: 0, duration: 0.6 }))
      return
    }
    run(() => gsap.fromTo(el, { opacity: 1 }, { opacity: 0, duration: 1, ease: 'power2.out' }))
    haptic(10)
  }, 420)
})

const terminalPropia = computed(() => esTerminalPropia(props.agent.pane_id))
const silencioErr = computed(() =>
  props.agent.session_id && silencioError.value?.sid === props.agent.session_id ? silencioError.value.texto : '',
)
const puedeIrAPc = computed(() => !!props.agent.session_id && esSesionTerminal(props.agent.pane_id))
const irAPcTexto = computed(() =>
  props.agent.session_id && irAPcAviso.value?.sid === props.agent.session_id ? irAPcAviso.value : null,
)
const silenciada = computed(() => !!props.agent.session_id && silenciadasGuardado.value.includes(props.agent.session_id))

const mudable = computed(
  () =>
    !esTerminalPropia(props.agent.pane_id) &&
    props.agent.kind === 'claude' &&
    !!props.agent.session_id &&
    (props.agent.status === 'idle' || props.agent.status === 'done') &&
    puedeMudar(props.agent.pane_id),
)
const marcando = ref(false)
async function marcarLeido() {
  const sid = props.agent.session_id
  if (!sid || marcando.value) return
  haptic(6)
  marcando.value = true
  try {
    await marcarPreguntaVista(sid)
  } catch {
    /* si falla, la pregunta sigue en pie y se puede reintentar */
  } finally {
    marcando.value = false
  }
}
function contestar() {
  if (!props.agent.session_id) return
  haptic(10)
  openSessionChat(props.agent.session_id)
}
</script>

<template>
  <div
    ref="root"
    class="agent"
    :data-st="efectivo"
    :data-pane="agent.pane_id"
    :class="{ open, clickable: canOpen, selected, unread: agent.unread }"
  >
    <i ref="flash" class="flash" aria-hidden="true" />
    <i ref="glow" class="glow" aria-hidden="true" />
    <div
      class="head"
      :role="canOpen ? 'button' : undefined"
      :tabindex="canOpen ? 0 : undefined"
      :aria-expanded="canOpen ? open : undefined"
      @click="toggle"
      @keydown.enter.prevent="toggle"
      @keydown.space.prevent="toggle"
    >
      <div class="line1">
        <span
          v-if="canOpen"
          class="tlink"
          role="link"
          tabindex="0"
          :aria-label="`Abrir el chat de ${title}`"
          @click.stop="openChat"
          @keydown.enter.stop.prevent="openChat"
          @keydown.space.stop.prevent="openChat"
        >
          <span class="title">{{ title }}</span>
          <Icon name="arrow-right" :size="13" class="tarrow" />
        </span>
        <span v-else class="title">{{ title }}</span>
        <span class="tfill" />
        <Icon v-if="silenciada" name="bell-off" :size="12" class="silencio-ind" />
        <span class="when mono">{{ when }}</span>
        <CtxRing v-if="agent.ctx" class="ctx-ring" :ctx="agent.ctx" :title="ctxText" />
      </div>
      <div v-if="meta" class="meta">
        <span v-if="agent.unread" ref="chip" class="new-chip"><i aria-hidden="true" />Nueva respuesta</span>
        <span v-if="agent.traba" class="traba-chip" role="status" :title="agent.traba.detalle"><Icon name="warn" :size="12" />{{ trabaRotulo }}</span>
        <StatusPill v-if="showPill" :status="efectivo" small />
        <button v-if="agent.asks_user" type="button" class="pide hit" aria-label="Abrir el chat de la sesión" @click.stop="contestar"><Icon name="ask" :size="12" />Te pregunta</button>
        <button v-if="agent.asks_user && canOpen" type="button" class="marcar-leido hit" :disabled="marcando" @click.stop="marcarLeido"><Icon name="check" :size="12" />Marcar leído</button>
        <button v-if="agent.pendiente && !agent.asks_user && canOpen" type="button" class="pendiente-chip hit" title="Marcada como leída: tocá para contestar" aria-label="Pendiente: abrir el chat para contestar" @click.stop="contestar"><i aria-hidden="true" />Pendiente</button>
        <button v-if="agent.status === 'blocked' && canOpen" type="button" class="respond hit" @click.stop="openChat">Responder</button>
        <button v-if="mr" type="button" class="mr-chip hit" :aria-label="`Abrir el MR !${mr.iid}`" @click.stop="irAMr(mr.ref)"><MrPipe :estado="mr.pipeline.estado" compact /><span class="mono">!{{ mr.iid }}</span></button>
        <span v-if="agent.kind && agent.kind !== 'claude'" class="kind mono">{{ agent.kind }}</span>
        <span v-if="resumenEnCabecera && showDoing" class="doing">{{ doing }}</span>
        <span v-if="resumenEnCabecera && fondoLinea" class="fondo mono">{{ fondoLinea }}</span>
      </div>
      <p v-if="silencioErr" class="silencio-err" role="alert">{{ silencioErr }}</p>
      <p v-if="irAPcTexto" class="ir-pc-aviso" :class="{ 'ir-pc-aviso--error': !irAPcTexto.ok }" role="status">{{ irAPcTexto.texto }}</p>
      <template v-if="resumenEnCabecera">
        <EstadoLineas v-if="estado" class="estado" :estado="estado" />
        <p v-else-if="pending" class="pending" :class="{ asks: agent.asks_user }">
          <Icon v-if="agent.asks_user" name="warn" :size="13" class="warn" />
          <span class="pending-text">{{ pending }}</span>
        </p>
      </template>
      <span v-if="canOpen" class="chev" aria-hidden="true"><Icon name="chevron" :size="14" /></span>
    </div>
    <div class="drawer" :aria-hidden="!open" :inert="!open">
      <div class="drawer-inner">
        <div class="panel">
          <div v-if="resumenEnCajon && (showDoing || fondoLinea || estado || pending)" class="resumen">
            <span v-if="showDoing" class="doing">{{ doing }}</span>
            <span v-if="fondoLinea" class="fondo mono">{{ fondoLinea }}</span>
            <EstadoLineas v-if="estado" class="estado" :estado="estado" />
            <p v-else-if="pending" class="pending" :class="{ asks: agent.asks_user }">
              <Icon v-if="agent.asks_user" name="warn" :size="13" class="warn" />
              <span class="pending-text">{{ pending }}</span>
            </p>
          </div>
          <p v-if="ctxText" class="ctx-line mono">{{ ctxText }}</p>
          <p v-if="usoText" class="ctx-line uso-line mono" title="Equivalente a precio de API, no lo que pagás con el plan">{{ usoText }}</p>
          <p v-if="terminalPropia" class="ctx-line mono">En tu terminal propia</p>
          <SessionPreview v-if="opened && agent.session_id && !pending" :agent="agent" />
          <div class="btns">
            <button v-if="mudable" type="button" class="act-btn" @click="abrirMudanza(agent.pane_id)"><Icon name="terminal" :size="15" /><span>Pasar a terminal propia</span></button>
            <button
              v-if="terminalPropia && vivoHabilitado"
              type="button"
              class="act-btn"
              @click="abrirVivo(agent.pane_id, title)"
            >
              <Icon name="terminal" :size="15" /><span>Ver terminal</span>
            </button>
            <button
              v-if="agent.session_id && !silenciada"
              type="button"
              class="act-btn"
              aria-label="Silenciar avisos"
              @click="silenciarSesion(agent.session_id, true)"
            >
              <Icon name="bell" :size="15" /><span>Silenciar</span>
            </button>
            <button
              v-else-if="agent.session_id"
              type="button"
              class="act-btn"
              aria-label="Volver a avisar"
              @click="silenciarSesion(agent.session_id, false)"
            >
              <Icon name="bell-off" :size="15" /><span>Avisar</span>
            </button>
            <button
              v-if="puedeIrAPc"
              type="button"
              class="act-btn"
              aria-label="Ir a PC"
              title="Abre una terminal en la notebook"
              :disabled="!!irAPcEnviando[agent.session_id!]"
              @click="irAPcSesion(agent.session_id!)"
            >
              <Icon name="monitor" :size="15" /><span>Ir a PC</span>
            </button>
            <button v-if="tabId && closable" type="button" class="act-btn act-btn--close" aria-label="Cerrar tab" @click="closeTab"><Icon name="close" :size="15" /><span>Cerrar</span></button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.flash {
  position: absolute;
  inset: 0;
  border-radius: var(--r-md);
  pointer-events: none;
  opacity: 0;
  transform-origin: left center;
  background: linear-gradient(90deg, color-mix(in srgb, var(--c) 30%, transparent), transparent 80%);
  box-shadow: inset 2px 0 0 var(--c);
}
.respond {
  height: 24px;
  padding: 0 10px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 620;
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-blocked) 40%, transparent);
  transition: scale 0.3s var(--spring), background 0.2s;
}
.pide {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px 0 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 620;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
  transition: scale 0.3s var(--spring), filter 0.2s;
}
.pide:hover {
  filter: brightness(1.1);
}
.marcar-leido {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 24px;
  padding: 0 10px 0 8px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 560;
  color: var(--text-3);
  background: transparent;
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: scale 0.3s var(--spring), background 0.2s, color 0.2s;
}
.marcar-leido:disabled {
  opacity: 0.55;
}
.marcar-leido:active {
  scale: var(--press-scale);
}
@media (hover: hover) and (pointer: fine) {
  .marcar-leido:hover {
    color: var(--text-2);
    background: var(--surface-hover);
  }
}
.pendiente-chip {
  border: none;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 19px;
  padding: 0 7px 0 6px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 560;
  color: var(--st-idle);
  background: var(--st-idle-soft);
  white-space: nowrap;
}
.pendiente-chip i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  opacity: 0.7;
}
.traba-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 20px;
  padding: 0 8px 0 6px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  white-space: nowrap;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  animation: traba-in 0.22s cubic-bezier(0.2, 0, 0, 1);
}
@keyframes traba-in {
  from { opacity: 0; transform: translateY(2px) scale(0.96); }
  to { opacity: 1; transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .traba-chip { animation: none; }
}
.pide:active,
.respond:active {
  scale: var(--press-scale);
}
.head {
  overflow: hidden;
}
.agent {
  --c: var(--st-idle);
  position: relative;
  border-radius: var(--r-md);
  transition: background 0.25s;
}
.agent[data-st='working'] { --c: var(--st-working); }
.agent[data-st='fondo'] { --c: var(--st-fondo); }
.agent[data-st='blocked'] { --c: var(--st-blocked); }
.agent[data-st='done'] { --c: var(--st-done); }
.agent[data-st='unknown'] { --c: var(--st-unknown); }

.head {
  position: relative;
  padding: 9px 30px 10px 12px;
  border-radius: var(--r-md);
  outline-offset: -2px;
}
.clickable .head {
  cursor: pointer;
}
@media (hover: hover) {
  .clickable .head:hover { background: var(--surface-hover); }
}
.head:focus-visible {
  outline: 1.5px solid var(--accent-line);
  outline-offset: -1.5px;
}
.selected .chev {
  color: var(--text);
}
.line1 {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}
.title {
  min-width: 0;
  font-weight: 560;
  font-size: 14px;
  line-height: 1.35;
  letter-spacing: -0.005em;
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow-wrap: anywhere;
}
.ctx-ring {
  padding-top: 2px;
}
.ctx-line {
  margin: 0;
  font-size: var(--t-sm);
  line-height: 1.4;
  color: var(--text-3);
}
.uso-line { font-variant-numeric: tabular-nums; color: var(--text-4); }
.when {
  flex: none;
  padding-top: 2px;
  font-size: 11px;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
}
.mr-chip { display: inline-flex; align-items: center; gap: 2px; height: 22px; padding: 0 8px 0 2px; border-radius: var(--r-pill); font-size: var(--t-sm); font-weight: 600; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); transition: background 0.2s, scale 0.3s var(--spring); }
.mr-chip:hover { background: var(--surface-hover); color: var(--text); }
.mr-chip:active { scale: var(--press-scale); }
.mr-chip :deep(.pipe) { box-shadow: none; background: transparent; }
.meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 8px;
  margin-top: 5px;
  min-width: 0;
}
/* Las etiquetas nunca se aprietan ni parten: si no entran, bajan de línea. */
.meta > :not(.doing) {
  flex-shrink: 0;
  white-space: nowrap;
}
.doing {
  flex: 1 1 9rem;
  min-width: 0;
  font-size: var(--t-md);
  color: var(--text-3);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fondo {
  flex: 1 1 100%;
  font-size: 12px;
  color: var(--st-fondo);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.kind {
  font-size: var(--t-xs);
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.pending {
  display: flex;
  gap: 6px;
  margin: 6px 0 0;
  font-size: 13px;
  line-height: 1.45;
  color: var(--text-2);
}
.estado {
  margin-top: 6px;
}
.pending-text {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
  overflow-wrap: anywhere;
  min-width: 0;
}
.open .pending-text {
  -webkit-line-clamp: 6;
  line-clamp: 6;
}
.pending.asks {
  color: var(--text);
}
.open .pending.asks {
  padding-left: 9px;
  box-shadow: inset 2px 0 0 var(--st-blocked);
}
.warn {
  flex: none;
  margin-top: 2px;
  color: var(--st-blocked);
}
.silencio-ind {
  flex: none;
  color: var(--text-4);
}
.silencio-err {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--danger);
}
.ir-pc-aviso {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-2);
}
.ir-pc-aviso--error {
  color: var(--danger);
}
.chev {
  position: absolute;
  top: 10px;
  right: 9px;
  color: var(--text-4);
  transition: transform 0.45s var(--spring), color 0.2s;
}
.head:hover .chev { color: var(--text-2); }
.open .chev {
  transform: rotate(90deg);
  color: var(--text-2);
}

.drawer {
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 0.28s var(--ease-out);
}
.open .drawer {
  grid-template-rows: 1fr;
}
.drawer-inner {
  min-height: 0;
  min-width: 0;
  overflow: hidden;
  margin: 0 12px;
  transition: opacity 0.2s var(--ease-out);
  opacity: 0;
}
.open .drawer-inner {
  opacity: 1;
}
.resumen {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  padding-bottom: 6px;
}
.resumen .doing {
  flex: none;
}
.resumen .fondo {
  flex: none;
}
.resumen .pending,
.resumen .estado {
  margin-top: 4px;
}
.resumen .estado :deep(.txt) {
  display: block;
  -webkit-line-clamp: unset;
  line-clamp: unset;
}
.panel {
  min-width: 0;
  display: grid;
  gap: 10px;
  padding-top: 12px;
  padding-bottom: 12px;
  border-top: 1px solid var(--line);
}
.btns {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.act-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 36px;
  padding: 0 11px;
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 560;
  color: var(--text-2);
  background: color-mix(in srgb, var(--bg-2) 70%, transparent);
  border: 1px solid transparent;
  white-space: nowrap;
  transition: color 0.2s, background 0.2s, border-color 0.2s, scale 0.25s var(--spring);
}
.act-btn :deep(svg) {
  color: var(--text-3);
  transition: color 0.2s;
}
@media (hover: hover) {
  .act-btn:hover {
    color: var(--text);
    background: var(--bg-2);
    border-color: var(--line-2);
  }
  .act-btn:hover :deep(svg) {
    color: var(--accent);
  }
  .act-btn--close:hover {
    color: var(--danger);
    border-color: color-mix(in srgb, var(--danger) 35%, transparent);
  }
  .act-btn--close:hover :deep(svg) {
    color: var(--danger);
  }
}
.act-btn:focus-visible {
  outline: 1.5px solid var(--accent-line);
  outline-offset: 1px;
}
.act-btn:active {
  scale: var(--press-scale);
}
.act-btn--close {
  color: var(--text-3);
}
.tlink {
  flex: 0 1 auto;
  min-width: 0;
  display: flex;
  align-items: flex-start;
  gap: 5px;
  cursor: pointer;
  border-radius: 6px;
  outline-offset: 2px;
}
.tfill { flex: 1 1 0; min-width: 0; }
.tlink .title {
  text-decoration: underline transparent;
  text-underline-offset: 3px;
  transition: text-decoration-color 0.2s, color 0.2s;
}
.tarrow {
  flex: none;
  margin-top: 3px;
  color: var(--text-3, var(--text-2));
  opacity: 0.55;
  transition: opacity 0.2s, translate 0.25s var(--spring), color 0.2s;
}
.tlink:focus-visible { outline: 1.5px solid var(--accent-line); }
.tlink:focus-visible .title { color: var(--accent); text-decoration-color: currentColor; }
@media (hover: hover) {
  .tlink .title { text-decoration-color: color-mix(in srgb, currentColor 22%, transparent); }
  .tarrow { opacity: 0; translate: -4px 0; }
  .tlink:hover .title { color: var(--accent); text-decoration-color: currentColor; }
  .tlink:hover .tarrow,
  .tlink:focus-visible .tarrow { opacity: 1; translate: 0 0; color: var(--accent); }
}
@media (hover: none) {
  .tlink { padding: 2px 4px 2px 0; margin: -2px 0; }
}

.new-chip {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 20px;
  padding: 0 8px 0 7px;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.01em;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.new-chip i {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  box-shadow: 0 0 8px var(--accent);
}
.glow {
  position: absolute;
  inset: -1px;
  border-radius: var(--r-md);
  pointer-events: none;
  opacity: 0;
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--accent) 55%, transparent), 0 0 26px -2px color-mix(in srgb, var(--accent) 70%, transparent);
}
</style>

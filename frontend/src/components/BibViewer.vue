<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { LibItem } from '../api/types'
import { diagramaOf, formatSize, KIND_LABEL, pathLabel, pruebasOf, reunionOf, resumenOf, safeClaudeUrl, viewerKind } from '../lib/biblioteca'
import { copyText } from '../lib/clipboard'
import { renderMarkdown } from '../lib/markdown'
import { clock } from '../lib/time'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { fresh, quitarItems, refreshItem } from '../state/biblioteca'
import { getLibraryText } from '../state/app'
import { useConfirmacionBoton } from '../lib/confirmacionBoton'
import BibFrame from './BibFrame.vue'
import BibImage from './BibImage.vue'
import BibQuitarSheet from './BibQuitarSheet.vue'
import DiagramaCard from './DiagramaCard.vue'
import Icon from './Icon.vue'
import PruebasCard from './PruebasCard.vue'
import ReunionCard from './ReunionCard.vue'
import ResumenCard from './ResumenCard.vue'

const props = defineProps<{
  item: LibItem
  hasPrev: boolean
  hasNext: boolean
  mode: 'panel' | 'overlay' | 'mobile'
}>()
const emit = defineEmits<{ close: []; prev: []; next: []; session: []; library: [] }>()

const kind = computed(() => viewerKind(props.item))
const claude = computed(() => safeClaudeUrl(props.item.url))
const title = computed(() => props.item.title || props.item.nombre || KIND_LABEL[props.item.kind])
const diagrama = computed(() => (kind.value === 'diagrama' ? diagramaOf(props.item) : null))
const pruebas = computed(() => (kind.value === 'pruebas' ? pruebasOf(props.item) : null))
const resumen = computed(() => (kind.value === 'resumen' ? resumenOf(props.item) : null))
const reunion = computed(() => (kind.value === 'reunion' ? reunionOf(props.item) : null))
const when = computed(() => {
  const t = Date.parse(props.item.ts)
  return Number.isNaN(t) ? '' : `${new Intl.DateTimeFormat('es-AR', { day: 'numeric', month: 'short' }).format(t)} · ${clock(t)}`
})

const root = ref<HTMLElement | null>(null)
const body = ref<HTMLElement | null>(null)
const src = ref('')
const nonce = ref(0)
const stalled = ref(false)
const loaded = ref(false)
const info = ref(false)
const isFull = ref(false)
const text = ref<string | null>(null)
const textError = ref(false)
const barHidden = ref(false)
const { run } = useGsap()
let hideTimer: ReturnType<typeof setTimeout> | undefined
let sequence = 0

const needsSrc = computed(() => ['frame', 'image', 'video', 'pdf'].includes(kind.value))
const mdHtml = computed(() => {
  if (text.value === null || !/\.md$/i.test(props.item.nombre)) return null
  return renderMarkdown(text.value)
})

async function load() {
  const mine = ++sequence
  stalled.value = false
  loaded.value = false
  text.value = null
  textError.value = false
  src.value = ''
  if (kind.value === 'text') {
    try {
      const t = await getLibraryText(props.item.id)
      if (mine === sequence) text.value = t
    } catch {
      if (mine === sequence) textError.value = true
    }
    return
  }
  if (!needsSrc.value) return
  const current = await fresh(props.item)
  if (mine === sequence) src.value = current.src
}

async function reload() {
  haptic(6)
  const mine = ++sequence
  stalled.value = false
  loaded.value = false
  const next = await refreshItem(props.item.id)
  if (mine !== sequence) return
  src.value = (next ?? props.item).src
  nonce.value++
}

watch(() => props.item.id, () => {
  load()
  info.value = false
  armHide()
  nextTick(enter)
}, { immediate: true })

function enter() {
  const el = body.value
  if (!el) return
  if (isSoft()) run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.15 }))
  else run(() => gsap.fromTo(el, { opacity: 0, y: 10, scale: 0.985 }, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'power3.out', clearProps: 'transform,opacity' }))
}

function onFrameLoad() {
  loaded.value = true
}

async function toggleFullscreen() {
  const el = root.value
  if (!el) return
  try {
    if (document.fullscreenElement) await document.exitFullscreen()
    else await el.requestFullscreen()
  } catch {
    isFull.value = !isFull.value
  }
}
function onFsChange() {
  isFull.value = document.fullscreenElement === root.value
}

function openPdf() {
  if (src.value) window.open(src.value, '_blank', 'noopener,noreferrer')
}

const asking = ref(false)
function askQuitar() {
  info.value = false
  asking.value = true
}
async function confirmQuitar() {
  asking.value = false
  haptic(8)
  await quitarItems([props.item.id])
}

const copiaRuta = useConfirmacionBoton()
async function copyPath() {
  copiaRuta.error.value = ''
  const ok = await copyText(pathLabel(props.item))
  if (!ok) return copiaRuta.fallo('No se pudo copiar la ruta')
  await copiaRuta.pulsarHecho()
}

function armHide() {
  clearTimeout(hideTimer)
  barHidden.value = false
  if (props.mode === 'mobile' && kind.value !== 'text') hideTimer = setTimeout(() => (barHidden.value = true), 3000)
}
function showBar() {
  if (barHidden.value) haptic(4)
  armHide()
}

defineExpose({ reload, toggleFullscreen, copyPath, isFull })
onMounted(() => document.addEventListener('fullscreenchange', onFsChange))
onBeforeUnmount(() => {
  document.removeEventListener('fullscreenchange', onFsChange)
  clearTimeout(hideTimer)
})
</script>

<template>
  <section ref="root" class="viewer" :class="[mode, { full: isFull, 'bar-hidden': barHidden }]" aria-label="Visor">
    <header class="bar">
      <button v-if="mode === 'overlay'" class="ic back" aria-label="Cerrar" @click="emit('close')"><Icon name="back" :size="17" /></button>
      <div class="titles">
        <b class="title" :title="title">{{ title }}</b>
        <span class="line">
          <i class="chip">{{ KIND_LABEL[item.kind] }}</i>
          <button class="sess" :title="`Ir a la sesión: ${item.session_titulo}`" @click="emit('session')">{{ item.session_titulo }}</button>
          <span class="mono muted">{{ when }}</span>
          <span v-if="item.version > 1" class="mono muted">v{{ item.version }}</span>
        </span>
      </div>
      <div class="actions">
        <button class="ic" :disabled="!hasPrev" aria-label="Anterior" title="Anterior ([)" @click="emit('prev')"><Icon name="prev" :size="15" /></button>
        <button class="ic" :disabled="!hasNext" aria-label="Siguiente" title="Siguiente (])" @click="emit('next')"><Icon name="next" :size="15" /></button>
        <button v-if="needsSrc || kind === 'text'" class="ic" aria-label="Recargar" title="Recargar (R)" @click="reload"><Icon name="refresh" :size="15" /></button>
        <button class="ic" :aria-label="isFull ? 'Salir de pantalla completa' : 'Pantalla completa'" title="Pantalla completa (F)" @click="toggleFullscreen">
          <Icon :name="isFull ? 'shrink' : 'expand'" :size="15" />
        </button>
        <a v-if="needsSrc && src" class="ic" :href="src" target="_blank" rel="noopener noreferrer" aria-label="Abrir en pestaña nueva" title="Abrir en pestaña nueva"><Icon name="external" :size="15" /></a>
        <a v-if="claude" class="ic claude" :href="claude" target="_blank" rel="noopener noreferrer" aria-label="Abrir en claude.ai" title="Abrir en claude.ai (O)">
          <svg viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden="true"><path d="m12 2 1.9 6.1L20 10l-6.1 1.9L12 18l-1.9-6.1L4 10l6.1-1.9z" /></svg>
        </a>
        <button class="ic" aria-label="Copiar ruta" title="Copiar ruta (C)" @click="copyPath"><Icon name="copy" :size="15" /></button>
        <button v-if="mode !== 'mobile'" class="ic del" aria-label="Quitar de la Biblioteca" title="Quitar de la Biblioteca (Supr)" @click="askQuitar"><Icon name="trash" :size="15" /></button>
        <button class="ic" :class="{ on: info }" aria-label="Detalles" :aria-expanded="info" title="Detalles" @click="info = !info"><Icon name="dots" :size="15" /></button>
        <button v-if="mode === 'panel' || mode === 'overlay'" class="ic" aria-label="Cerrar" title="Cerrar (Esc)" @click="emit('close')"><Icon name="close" :size="15" /></button>
      </div>
    </header>
    <button v-if="mode === 'mobile'" class="volver" aria-label="Volver a la lista" @click="emit('close')"><Icon name="back" :size="17" /><span>Volver</span></button>
    <button v-if="mode === 'mobile'" class="edge" aria-label="Mostrar barra" @click="showBar" />

    <Transition name="drop">
      <dl v-if="info" class="info">
        <template v-if="item.description || item.caption"><dt>Descripción</dt><dd>{{ item.description || item.caption }}</dd></template>
        <dt>Ruta</dt><dd class="mono">{{ pathLabel(item) }}</dd>
        <dt>Tamaño</dt><dd class="mono">{{ formatSize(item.size) }}</dd>
        <template v-if="item.versions.length > 1">
          <dt>Versiones</dt>
          <dd class="mono">{{ item.versions.map((v) => `v${v.version}`).join(' · ') }}</dd>
        </template>
        <template v-if="!item.copia && kind !== 'remote'"><dt>Copia local</dt><dd>No hay: si el archivo se borra, se pierde.</dd></template>
        <template v-if="mode === 'overlay'">
          <dt /><dd><button class="link" @click="emit('library')">Ver en la Biblioteca</button></dd>
        </template>
        <template v-if="mode === 'mobile'">
          <dt /><dd><button class="link danger" @click="askQuitar"><Icon name="trash" :size="13" /> Quitar de la Biblioteca</button></dd>
        </template>
      </dl>
    </Transition>

    <div ref="body" class="body">
      <template v-if="kind === 'frame'">
        <div v-if="!loaded" class="skeleton sk-sweep" aria-hidden="true" />
        <BibFrame v-if="src" :key="nonce" :src="src" :title="title" @load="onFrameLoad" @stalled="stalled = true" />
        <Transition name="fade">
          <div v-if="stalled && !loaded" class="stall">
            <p>La página tarda en cargar o el enlace venció.</p>
            <button class="btn" @click="reload"><Icon name="refresh" :size="14" /> Recargar</button>
          </div>
        </Transition>
        <p v-if="mode === 'panel' && loaded" class="hint">Clic afuera o <kbd>Esc</kbd> dos veces para volver a los atajos</p>
      </template>
      <BibImage v-else-if="kind === 'image' && src" :key="nonce" :src="src" :alt="title" />
      <video v-else-if="kind === 'video' && src" :key="nonce" class="media" :src="src" controls playsinline preload="metadata" />
      <div v-else-if="kind === 'pdf'" class="note">
        <Icon name="doc" :size="30" />
        <p>{{ item.nombre }}</p>
        <p class="muted">{{ formatSize(item.size) }}</p>
        <button class="btn primary" :disabled="!src" @click="openPdf">Abrir PDF</button>
      </div>
      <div v-else-if="kind === 'text'" class="doc">
        <div v-if="mdHtml !== null" class="md" v-html="mdHtml" />
        <pre v-else-if="text !== null" class="plain mono">{{ text }}</pre>
        <p v-else-if="textError" class="muted">No pude leer el archivo.</p>
        <div v-else class="skeleton lines sk-sweep" aria-hidden="true" />
      </div>
      <div v-else-if="kind === 'diagrama'" class="doc diagrama">
        <DiagramaCard v-if="diagrama" :diagrama="diagrama" />
        <div v-else class="note">
          <Icon name="diagrama" :size="30" />
          <p>Diagrama (no se pudo leer)</p>
          <pre class="plain mono">{{ item.diagrama_raw }}</pre>
        </div>
      </div>
      <div v-else-if="kind === 'pruebas'" class="doc diagrama">
        <PruebasCard v-if="pruebas" :data="pruebas" :evidencias="item.evidencias" />
        <div v-else class="note">
          <Icon name="warn" :size="30" />
          <p>No pude leer este informe de pruebas.</p>
        </div>
      </div>
      <div v-else-if="kind === 'reunion'" class="doc diagrama">
        <ReunionCard v-if="reunion" :data="reunion" :item-id="item.id" :tiene-charla="item.tiene_charla === true" />
        <div v-else class="note">
          <Icon name="warn" :size="30" />
          <p>No pude leer esta reunión.</p>
        </div>
      </div>
      <div v-else-if="kind === 'resumen'" class="doc diagrama">
        <ResumenCard v-if="resumen" :data="resumen" :item-id="item.id" />
        <div v-else class="note">
          <Icon name="warn" :size="30" />
          <p>No pude leer este resumen.</p>
        </div>
      </div>
      <div v-else-if="kind === 'remote'" class="note">
        <Icon name="external" :size="30" />
        <p>Esta página solo está en claude.ai.</p>
        <a v-if="claude" class="btn primary" :href="claude" target="_blank" rel="noopener noreferrer">Abrir en claude.ai</a>
      </div>
      <div v-else class="note">
        <Icon name="warn" :size="30" />
        <p>{{ item.motivo || 'No se puede mostrar este archivo.' }}</p>
        <a v-if="claude" class="btn" :href="claude" target="_blank" rel="noopener noreferrer">Abrir en claude.ai</a>
      </div>
    </div>

    <footer class="seal mono">Contenido de una sesión · aislado</footer>
    <BibQuitarSheet :open="asking" :count="1" :name="title" @confirm="confirmQuitar" @cancel="asking = false" />
  </section>
</template>

<style scoped>
.viewer {
  position: relative;
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  height: 100%;
  min-height: 0;
  background: var(--bg);
  overflow: hidden;
}
.viewer.full {
  position: fixed;
  inset: 0;
  z-index: 400;
}
.bar {
  grid-row: 1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--line);
  background: color-mix(in srgb, var(--bg) 86%, transparent);
  backdrop-filter: blur(10px);
  z-index: 3;
  transition: transform 0.4s var(--ease-out), opacity 0.3s;
}
.mobile .bar {
  position: absolute;
  inset: 0 0 auto 0;
  padding-top: max(10px, env(safe-area-inset-top));
}
.mobile.bar-hidden .bar {
  transform: translateY(-100%);
  opacity: 0;
  pointer-events: none;
}
.volver {
  position: absolute;
  top: max(10px, env(safe-area-inset-top));
  left: max(12px, env(safe-area-inset-left));
  z-index: 6;
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 40px;
  padding: 0 14px 0 10px;
  border-radius: var(--r-pill);
  font-size: 14px;
  font-weight: 600;
  color: var(--text);
  background: color-mix(in srgb, var(--surface-2) 88%, transparent);
  backdrop-filter: blur(10px);
  box-shadow: 0 6px 20px -8px rgba(0, 0, 0, 0.5), inset 0 0 0 1px var(--line-2);
  transition: scale 0.3s var(--spring);
}
.volver:active { scale: var(--press-scale); }
.mobile .bar {
  padding-left: calc(max(12px, env(safe-area-inset-left)) + 104px);
}
.edge {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 24px;
  z-index: 4;
}
.mobile .body {
  grid-row: 1 / 3;
}
.titles {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 1px;
}
.title {
  font-family: var(--font-display);
  font-weight: 600;
  font-size: 15px;
  letter-spacing: -0.015em;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.line {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  font-size: var(--t-sm);
  color: var(--text-3);
  white-space: nowrap;
}
.chip {
  font-style: normal;
  font-size: var(--t-xs);
  font-weight: 560;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  color: var(--accent);
  background: var(--accent-soft);
}
.sess {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-2);
  text-decoration: underline dotted var(--line-2);
  text-underline-offset: 3px;
}
.sess:hover {
  color: var(--accent);
}
.muted {
  color: var(--text-4);
}
.actions {
  flex: none;
  display: flex;
  align-items: center;
  gap: 2px;
}
.ic {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--r-md);
  color: var(--text-2);
  transition: color 0.2s, background 0.2s, scale 0.3s var(--spring);
}
.ic:hover:not(:disabled),
.ic.on {
  color: var(--text);
  background: var(--surface-hover);
}
.ic:active:not(:disabled) {
  scale: var(--press-scale);
}
.ic:disabled {
  opacity: 0.3;
  cursor: default;
}
.ic.del:hover {
  color: var(--danger);
}
.ic.claude:hover {
  color: var(--accent);
}
.ic svg {
  width: 17px;
  height: 17px;
}
.mobile .actions .ic:nth-child(n + 4):not(:last-child) {
  display: none;
}
.info {
  position: absolute;
  top: 56px;
  right: 12px;
  z-index: 5;
  width: min(360px, calc(100% - 24px));
  margin: 0;
  padding: 14px 16px;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 6px 14px;
  font-size: var(--t-md);
  border-radius: var(--r-lg);
  background: var(--surface-2);
  box-shadow: var(--shadow-pop);
}
.mobile .info {
  top: max(56px, calc(env(safe-area-inset-top) + 48px));
}
.info dt {
  color: var(--text-3);
}
.info dd {
  margin: 0;
  min-width: 0;
  overflow-wrap: anywhere;
}
.link {
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}
.link.danger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--danger);
  text-decoration: none;
}
.drop-enter-active { transition: transform 0.45s var(--spring), opacity 0.2s; }
.drop-leave-active { transition: opacity 0.15s; }
.drop-enter-from { transform: translateY(-8px) scale(0.97); opacity: 0; }
.drop-leave-to { opacity: 0; }
.fade-enter-active, .fade-leave-active { transition: opacity 0.25s; }
.fade-enter-from, .fade-leave-to { opacity: 0; }

.body {
  position: relative;
  grid-row: 2;
  min-height: 0;
  overflow: hidden;
}
.body :deep(iframe.frame) {
  position: absolute;
  inset: 0;
}
.media {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  background: #000;
}
.skeleton {
  position: absolute;
  inset: 0;
  --sk-bg: linear-gradient(100deg, var(--surface) 30%, var(--surface-2) 50%, var(--surface) 70%);
  --sk-left: -440%;
  --sk-w: 660%;
  --sk-tile: 33.3333%;
  --sk-dx: 40%;
  --sk-dur: 1.4s;
}
.skeleton.lines {
  position: relative;
  height: 160px;
  border-radius: 12px;
}
:root[data-motion='soft'] .skeleton::after {
  animation: none;
}
.stall,
.note {
  position: absolute;
  inset: 0;
  display: grid;
  align-content: center;
  justify-items: center;
  gap: 12px;
  padding: 24px;
  text-align: center;
  color: var(--text-2);
}
.stall {
  background: color-mix(in srgb, var(--bg) 80%, transparent);
  z-index: 2;
}
.note svg {
  color: var(--accent);
}
.note p,
.stall p {
  margin: 0;
}
.btn {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 36px;
  padding: 0 16px;
  border-radius: var(--r-pill);
  font-size: var(--t-lg);
  color: var(--text);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, box-shadow 0.2s, scale 0.3s var(--spring);
}
.btn:hover {
  background: var(--surface-hover);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.btn:active {
  scale: var(--press-scale);
}
.btn.primary {
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: none;
}
.hint {
  position: absolute;
  left: 50%;
  bottom: 10px;
  translate: -50% 0;
  margin: 0;
  padding: 4px 12px;
  border-radius: var(--r-pill);
  font-size: 11px;
  color: var(--text-3);
  background: color-mix(in srgb, var(--bg) 82%, transparent);
  backdrop-filter: blur(6px);
  pointer-events: none;
  animation: hint 6s 0.6s both;
}
@keyframes hint {
  0%, 85% { opacity: 1; }
  100% { opacity: 0; }
}
kbd {
  font-family: var(--font-mono);
  font-size: var(--t-xs);
  padding: 0 5px;
  border-radius: 4px;
  box-shadow: inset 0 0 0 1px var(--line-2);
}
.doc {
  position: absolute;
  inset: 0;
  overflow: auto;
  overscroll-behavior: contain;
  padding: 24px clamp(16px, 4vw, 40px);
  max-width: 820px;
  margin: 0 auto;
}
.mobile .doc {
  padding-top: calc(72px + env(safe-area-inset-top));
}
.doc.diagrama {
  max-width: none;
  padding: 16px;
}
.mobile .doc.diagrama {
  padding: calc(64px + env(safe-area-inset-top)) 16px calc(16px + env(safe-area-inset-bottom));
}
.plain {
  margin: 0;
  font-size: var(--t-md);
  line-height: 1.6;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
.seal {
  grid-row: 3;
  padding: 5px 14px;
  font-size: 10px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-4);
  border-top: 1px solid var(--line);
  text-align: right;
}
.mobile .seal {
  display: none;
}
@media (pointer: coarse) {
  .ic { min-width: 44px; min-height: 44px; }
}
</style>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, onBeforeUnmount, onMounted, ref, watch, type PropType } from 'vue'
import { clavesDeLineas, nuevoReusoClaves, type AnsiLine, type AnsiSpan } from '../lib/ansi'
import Icon from './Icon.vue'

const props = defineProps<{ lines: AnsiLine[]; truncado: boolean }>()

const clase = (sp: AnsiSpan) => (sp.b || sp.d || sp.i || sp.u || sp.s ? `sp${sp.b ? ' b' : ''}${sp.d ? ' d' : ''}${sp.i ? ' it' : ''}${sp.u ? ' u' : ''}${sp.s ? ' s' : ''}` : 'sp')
const Linea = defineComponent({
  props: { line: { type: Array as PropType<AnsiLine>, required: true } },
  setup: (p) => () =>
    h('span', { class: 'ln' }, [
      ...p.line.map((sp) => h('span', { class: clase(sp), style: sp.fg || sp.bg ? { color: sp.fg, backgroundColor: sp.bg } : undefined }, sp.t)),
      '\n',
    ]),
})
const reuso = nuevoReusoClaves()
const claves = computed(() => reuso(clavesDeLineas(props.lines)))

const NEAR = 60
const WRAP_KEY = 'orq.terminal.wrap'
const wrap = ref(initialWrap())
function initialWrap(): boolean {
  try {
    const saved = localStorage.getItem(WRAP_KEY)
    if (saved === '1' || saved === '0') return saved === '1'
  } catch {
    /* sin almacenamiento */
  }
  return typeof matchMedia === 'undefined' ? false : matchMedia('(max-width: 1023px)').matches
}
function toggleWrap() {
  wrap.value = !wrap.value
  try {
    localStorage.setItem(WRAP_KEY, wrap.value ? '1' : '0')
  } catch {
    /* sin almacenamiento */
  }
  void nextTick(() => stick.value && toBottom())
}
const scroller = ref<HTMLElement | null>(null)
const stick = ref(true)
const showJump = ref(false)

const near = () => {
  const el = scroller.value
  return !el || el.scrollHeight - el.scrollTop - el.clientHeight < NEAR
}
function onScroll() {
  if (near()) {
    stick.value = true
    showJump.value = false
  } else stick.value = false
}
function toBottom() {
  const el = scroller.value
  if (!el) return
  el.scrollTop = el.scrollHeight
  stick.value = true
  showJump.value = false
}
watch(
  () => props.lines,
  async () => {
    await nextTick()
    if (stick.value) toBottom()
    else showJump.value = true
  },
)
let ro: ResizeObserver | null = null
onMounted(() => {
  toBottom()
  if (scroller.value && typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(() => stick.value && toBottom())
    ro.observe(scroller.value)
  }
})
onBeforeUnmount(() => ro?.disconnect())
defineExpose({ toBottom })
</script>

<template>
  <div class="tout-wrap">
    <div ref="scroller" class="tout" tabindex="0" role="log" aria-label="Salida de la terminal" data-noswipe @scroll.passive="onScroll">
      <p v-if="truncado" class="cut mono">… salida recortada: se muestran las últimas líneas</p>
      <div v-if="!lines.length" class="empty mono">Sin salida todavía</div>
      <pre v-else class="tpre" :class="{ wrap }"><Linea v-for="(line, i) in lines" :key="claves[i]" :line="line" /></pre>
    </div>
    <button type="button" class="wrapbtn" :aria-pressed="wrap" @click="toggleWrap"><Icon name="list" :size="13" /><span>Ajustar líneas</span></button>
    <Transition name="jump">
      <button v-if="showJump" type="button" class="jump" aria-label="Ir al final" @click="toBottom"><Icon name="down" :size="16" /></button>
    </Transition>
  </div>
</template>

<style scoped>
.tout-wrap { position: relative; flex: 1; min-width: 0; min-height: 0; display: flex; }
.tout {
  flex: 1;
  min-width: 0;
  overflow: auto;
  overscroll-behavior: contain;
  overflow-anchor: none;
  padding: 40px 14px 16px;
  background: var(--term-bg);
  color: var(--term-fg);
  box-shadow: inset 0 0 0 1px var(--line);
  -webkit-overflow-scrolling: touch;
}
.tout:focus-visible { outline: 2px solid var(--accent-line); outline-offset: -2px; }
.tpre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--t-md);
  line-height: 1.45;
  white-space: pre;
  tab-size: 8;
  width: max-content;
  min-width: 100%;
}
.tpre.wrap { white-space: pre-wrap; overflow-wrap: anywhere; width: auto; min-width: 0; }
.wrapbtn {
  position: absolute;
  top: 8px;
  right: 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 26px;
  padding: 0 10px;
  border-radius: var(--r-pill);
  font-size: 12px;
  color: var(--text-2);
  background: color-mix(in srgb, var(--surface) 88%, transparent);
  box-shadow: inset 0 0 0 1px var(--line-2);
  backdrop-filter: blur(8px);
}
.wrapbtn[aria-pressed='true'] { color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent-line); }
.tpre :deep(.sp.b) { font-weight: 700; }
.tpre :deep(.sp.d) { opacity: 0.6; }
.tpre :deep(.sp.it) { font-style: italic; }
.tpre :deep(.sp.u) { text-decoration: underline; }
.tpre :deep(.sp.s) { text-decoration: line-through; }
.tpre :deep(.sp.u.s) { text-decoration: underline line-through; }
.cut, .empty { margin: 0 0 8px; font-size: var(--t-sm); color: var(--text-3); }
.jump {
  position: absolute;
  right: 16px;
  bottom: 14px;
  width: 38px;
  height: 38px;
  border-radius: 50%;
  display: grid;
  place-items: center;
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: var(--shadow-pop);
}
.jump-enter-active { transition: transform 0.4s var(--spring), opacity 0.2s; }
.jump-leave-active { transition: opacity 0.15s; }
.jump-enter-from { transform: scale(0.6); opacity: 0; }
.jump-leave-to { opacity: 0; }
@media (max-width: 1023px) { .tpre { font-size: var(--t-sm); } }
</style>

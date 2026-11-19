<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, useId, watch } from 'vue'
import { enterKeyState, keyShapes, type EnterMode } from '../lib/enterKey'
import { gsap, haptic, isSoft, ring, useGsap } from '../motion'

const props = withDefaults(
  defineProps<{ mode?: EnterMode; disabled?: boolean; busy?: boolean; label?: string; stopLabel?: string; title?: string; tone?: 'accent' | 'danger' | 'neutral' }>(),
  { mode: 'send', tone: 'accent' },
)
const emit = defineEmits<{ stop: [] }>()

const st = computed(() => enterKeyState(props))
const pad = ref<HTMLDivElement | null>(null)
const btn = ref<HTMLButtonElement | null>(null)
const glyph = ref<SVGElement | null>(null)
const gid = `ek-${useId()}`
const geom = reactive({ w: 69, h: 82, wing: 32, stem: 52, r: 10, depth: 3, bevel: 3 })
const shapes = computed(() => keyShapes(geom))
const { run } = useGsap()

const px = (s: CSSStyleDeclaration, k: string, d: number) => parseFloat(s.getPropertyValue(k)) || d
let ro: ResizeObserver | null = null
function measure() {
  const b = btn.value
  const p = pad.value
  if (!b || !p) return
  const s = getComputedStyle(p)
  Object.assign(geom, {
    w: b.clientWidth,
    h: b.clientHeight,
    wing: px(s, '--wing', 32),
    stem: px(s, '--stem', 52),
    r: px(s, '--r', 10),
    depth: px(s, '--depth', 3),
    bevel: px(s, '--bevel', 3),
  })
}
onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined' && btn.value) {
    ro = new ResizeObserver(measure)
    ro.observe(btn.value)
  }
})
onBeforeUnmount(() => ro?.disconnect())

function onClick() {
  if (props.mode === 'stop') emit('stop')
}

function fire() {
  const b = btn.value
  const g = glyph.value
  if (!b || !g || isSoft()) return
  haptic(8)
  ring(b, getComputedStyle(b).getPropertyValue('--face'), 46)
  run(() =>
    gsap
      .timeline()
      .to(b, { '--kick': '3px', duration: 0.07, ease: 'power2.out' })
      .to(b, { '--kick': '0px', duration: 0.6, ease: 'elastic.out(1.2, 0.35)' })
      .to(g, { x: 12, opacity: 0, duration: 0.14, ease: 'power2.in' }, 0)
      .fromTo(g, { x: -12, opacity: 0 }, { x: 0, opacity: 1, duration: 0.4, ease: 'back.out(2)' }, 0.16),
  )
}

// Al cambiar enviar↔freno la tecla se hunde apenas y el glifo nuevo entra girando; el color ya cruza por CSS.
watch(
  () => props.mode,
  async () => {
    await nextTick()
    const b = btn.value
    const g = glyph.value
    if (!b || !g || isSoft()) return
    const toStop = props.mode === 'stop'
    run(() =>
      gsap
        .timeline()
        .to(b, { '--kick': '2px', duration: 0.09, ease: 'power2.out' })
        .to(b, { '--kick': '0px', duration: 0.55, ease: 'elastic.out(1.1, 0.4)' })
        .fromTo(
          g,
          { scale: 0.3, rotation: toStop ? -90 : 90, opacity: 0, svgOrigin: '0 0' },
          { scale: 1, rotation: 0, opacity: 1, duration: 0.42, ease: 'back.out(2.2)', svgOrigin: '0 0' },
          0.04,
        ),
    )
  },
)

defineExpose({ fire })
</script>

<template>
  <div ref="pad" class="pad" :class="`tone-${tone}`">
    <div class="hole"><slot /></div>
    <button
      ref="btn"
      class="enter"
      :class="{ stop: mode === 'stop', busy }"
      :type="st.type"
      :disabled="st.disabled"
      :aria-label="st.label"
      :title="title"
      @click="onClick"
    >
      <svg class="key" :width="geom.w" :height="geom.h" :viewBox="`0 0 ${geom.w} ${geom.h}`" aria-hidden="true">
        <defs>
          <linearGradient :id="gid" gradientUnits="userSpaceOnUse" x1="0" y1="0" x2="0" :y2="geom.wing">
            <stop offset="0" class="hi" />
            <stop offset="1" class="lo" />
          </linearGradient>
        </defs>
        <path class="focus" :d="shapes.ring" />
        <path class="skirt" :d="shapes.skirt" />
        <g class="cap">
          <path class="body" :d="shapes.body" />
          <path class="face" :d="shapes.face" :style="{ fill: `url(#${gid})` }" />
          <g :transform="`translate(${shapes.glyph.x} ${shapes.glyph.y})`">
            <g v-if="st.glyph === 'spin'" class="spin"><circle r="7" fill="none" stroke="currentColor" stroke-width="1.6" stroke-dasharray="33 11" stroke-linecap="round" /></g>
            <g v-else-if="st.glyph === 'stop'" ref="glyph"><rect x="-5.5" y="-5.5" width="11" height="11" rx="2.2" fill="currentColor" /></g>
            <g v-else ref="glyph"><path d="M7 -6v5a3 3 0 0 1-3 3h-11.5M-4 -2l-4 4 4 4" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" stroke-linejoin="round" /></g>
          </g>
        </g>
      </svg>
    </button>
  </div>
</template>

<style scoped>
.pad {
  --mic: 44px;
  --over: 12px;
  --gap: 5px;
  --stem: 52px;
  --wing: 32px;
  --r: 10px;
  --depth: 3px;
  --bevel: 3px;
  --face: var(--accent);
  --ink: var(--accent-ink);
  position: relative;
  flex: none;
  align-self: stretch;
  display: grid;
  grid-template-columns: calc(var(--mic) - var(--over)) calc(var(--over) + var(--gap)) var(--stem);
  grid-template-rows: calc(var(--wing) + var(--depth)) 1fr;
  min-height: calc(var(--wing) + var(--gap) + var(--mic) + var(--depth) * 2);
}
@media (min-width: 1024px) {
  .pad { --mic: 40px; --over: 11px; --gap: 4px; --stem: 46px; --wing: 28px; --r: 9px; }
}
.tone-danger { --face: var(--danger); --ink: var(--danger-ink, #fff); }
.tone-neutral { --face: var(--text); --ink: var(--bg); }
.hole {
  grid-area: 2 / 1 / 3 / 3;
  display: grid;
  padding: var(--gap) var(--gap) var(--depth) 0;
  min-width: 0;
}
.enter {
  --kick: 0px;
  --lift: 0px;
  grid-area: 1 / 2 / 3 / 4;
  position: relative;
  pointer-events: none;
  color: var(--ink);
  outline: none;
  -webkit-tap-highlight-color: transparent;
}
.enter:disabled {
  --face: color-mix(in srgb, var(--text) 9%, var(--surface));
  --ink: var(--text-4);
  cursor: default;
}
.key {
  position: absolute;
  inset: 0;
  overflow: visible;
}
.skirt, .body {
  pointer-events: visiblePainted;
  cursor: pointer;
}
.enter:disabled .skirt, .enter:disabled .body { cursor: not-allowed; }
.skirt { fill: color-mix(in srgb, var(--face) 48%, #000); transition: fill 0.3s; }
.body { fill: color-mix(in srgb, var(--face) 76%, #000); transition: fill 0.3s; }
.hi { stop-color: color-mix(in srgb, var(--face) 80%, #fff); transition: stop-color 0.3s; }
.lo { stop-color: var(--face); transition: stop-color 0.3s; }
/* Apagada, el brillo del ala la separaba del tallo y la tecla se leía como dos piezas. */
.enter:disabled .hi { stop-color: color-mix(in srgb, var(--face) 95%, #fff); }
.cap {
  transform: translateY(calc(var(--lift) + var(--kick)));
  transition: transform 0.35s var(--spring), opacity 0.2s;
}
.focus { fill: none; stroke: var(--text); stroke-width: 2; opacity: 0; }
.enter:focus-visible .focus { opacity: 1; }
.enter:hover:not(:disabled) { --lift: -1px; }
.enter:active:not(:disabled) { --lift: calc(var(--depth) - 1px); }
.enter:active:not(:disabled) .cap { transition-duration: 0.08s; }
.stop:not(:disabled) .cap { animation: breathe 1.6s ease-in-out infinite; }
.stop:disabled { --face: color-mix(in srgb, var(--text) 16%, var(--surface)); --ink: var(--text-3); }
.spin { animation: spin 0.8s linear infinite; }
@keyframes spin { to { transform: rotate(360deg); } }
@keyframes breathe { 50% { opacity: 0.84; } }
@media (prefers-reduced-motion: reduce) {
  .stop .cap { animation: none; }
}
:root[data-motion='soft'] .stop:not(:disabled) .cap {
  animation: none;
}
</style>

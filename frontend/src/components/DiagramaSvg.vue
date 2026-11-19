<script setup lang="ts">
import { computed, onBeforeUnmount, ref, useId } from 'vue'
import type { EArista, ENodo, Escena, Etiqueta } from '../lib/escena'
import { gsap, useGsap } from '../motion'

const props = defineProps<{
  escena: Escena
  /** keys that stay lit; null = nothing is singled out */
  foco?: Set<string> | null
  sel?: string | null
  titulo?: string
  /** draw at this size (px); the viewBox keeps it crisp */
  ancho?: number
  alto?: number
  /** no pointer interaction (thumbnails) */
  estatico?: boolean
}>()
const emit = defineEmits<{ tocar: [key: string | null]; sobre: [key: string | null] }>()

const uid = useId()
const svg = ref<SVGSVGElement | null>(null)
const { run } = useGsap()

const LH = 17
const ELH = 14

const rr = (w: number, h: number, r: number) => {
  const k = Math.min(r, w / 2, h / 2)
  return `M${k},0H${w - k}A${k},${k} 0 0 1 ${w},${k}V${h - k}A${k},${k} 0 0 1 ${w - k},${h}H${k}A${k},${k} 0 0 1 0,${h - k}V${k}A${k},${k} 0 0 1 ${k},0Z`
}

interface Pinta {
  n: ENodo
  forma: string
  d: string
  extra: string
  tx: number
  ty: number[]
  subY: number
  icon: { x: number; y: number } | null
  px: number
  peso: number
}

function pintar(n: ENodo): Pinta {
  const { w, h } = n
  let d = rr(w, h, 12)
  let extra = ''
  let cy = h / 2
  let px = 13
  let peso = 600
  switch (n.forma) {
    case 'persona':
    case 'terminal':
      d = rr(w, h, h / 2)
      if (n.forma === 'terminal') px = 12
      break
    case 'servicio':
      d = rr(w, h, 7)
      break
    case 'actor':
      d = rr(w, h, 14)
      break
    case 'datos': {
      const e = 7
      d = `M0,${e}A${w / 2},${e} 0 0 1 ${w},${e}V${h - e}A${w / 2},${e} 0 0 1 0,${h - e}Z`
      extra = `M0,${e}A${w / 2},${e} 0 0 0 ${w},${e}`
      cy += 4
      break
    }
    case 'nota':
      d = `M0,0H${w - 14}L${w},14V${h}H0Z`
      extra = `M${w - 14},0V14H${w}`
      peso = 500
      break
    case 'decision':
      d = `M${w / 2},0L${w},${h / 2}L${w / 2},${h}L0,${h / 2}Z`
      break
  }
  const conIcono = !!n.icono && n.forma !== 'decision' && n.forma !== 'terminal'
  const pad = n.forma === 'persona' ? 18 : 14
  const tx = conIcono ? (pad + 30 + w - pad) / 2 : w / 2
  const th = n.lineas.length * LH + (n.sub ? 15 : 0)
  const y0 = cy - th / 2 + 12.5
  return {
    n,
    forma: n.forma,
    d,
    extra,
    tx,
    ty: n.lineas.map((_, i) => y0 + i * LH),
    subY: y0 + n.lineas.length * LH + 1,
    icon: conIcono ? { x: pad - 3, y: cy - 13 } : null,
    px,
    peso,
  }
}

const nodos = computed(() => props.escena.nodos.map(pintar))
const lineasEt = (l: Etiqueta) => {
  const y0 = l.y + l.h / 2 - (l.lineas.length * ELH) / 2 + 10.5
  return l.lineas.map((t, i) => ({ t, y: y0 + i * ELH }))
}
const aristas = computed(() => props.escena.aristas.map((a) => ({ a, et: a.etiqueta ? lineasEt(a.etiqueta) : [] })))
const seq = computed(() => props.escena.tipo === 'secuencia')

const apagado = (k: string) => !!props.foco && !props.foco.has(k)
const encendido = (k: string) => !!props.foco && props.foco.has(k)
const clsA = (a: EArista) => [`tr-${a.trazo}`, { dim: apagado(a.key), lit: encendido(a.key), sel: props.sel === a.key, propia: a.propia }]

function tocar(k: string | null) {
  if (!props.estatico) emit('tocar', k)
}
function sobre(k: string | null) {
  if (!props.estatico) emit('sobre', k)
}

// ---------- motion ----------
const q = (s: string) => Array.from(svg.value?.querySelectorAll<SVGElement>(s) ?? [])
const PARTES = '.gr, .ll, .nd-in, .ln, .pt, .et, .num'

/** Hides everything until the entrance plays, so nothing flashes first. */
function ocultar() {
  run(() => gsap.set(q(PARTES), { opacity: 0 }))
}

let entrada: gsap.core.Timeline | null = null

/** Jumps to the final state: used when the tab is in the background (no frames) or the scene changed mid-entrance. */
function mostrar() {
  entrada?.kill()
  entrada = null
  run(() => gsap.set(q(PARTES), { clearProps: 'all' }))
}

function entrar(soft: boolean): gsap.core.Timeline | null {
  if (typeof document !== 'undefined' && document.hidden) {
    mostrar()
    return null
  }
  entrada?.kill()
  return (entrada = run(() => {
    const tl = gsap.timeline({ onComplete: () => (entrada = null) })
    const todo = q(PARTES)
    if (soft) {
      tl.fromTo(todo, { opacity: 0 }, { opacity: 1, duration: 0.35, ease: 'power1.out', clearProps: 'opacity' })
      return tl
    }
    const e = props.escena
    const maxRank = Math.max(1, ...e.nodos.map((n) => n.rank), ...(seq.value ? e.aristas.map((a) => a.rank) : [0]))
    const paso = seq.value ? Math.min(0.2, 2.2 / maxRank) : Math.min(0.16, 1.3 / maxRank)
    const tNodo = (r: number) => (seq.value ? 0 : 0.1 + r * paso)
    tl.fromTo(q('.gr'), { opacity: 0, scale: 0.975, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.7, stagger: 0.08, ease: 'power2.out', clearProps: 'all' }, 0)
    const enRank = new Map<number, number>()
    for (const el of q('.nd-in')) {
      const r = Number(el.dataset.r ?? 0)
      const k = enRank.get(r) ?? 0
      enRank.set(r, k + 1)
      tl.fromTo(el, { opacity: 0, y: 10, scale: 0.9, transformOrigin: '50% 50%' }, { opacity: 1, y: 0, scale: 1, duration: 0.6, ease: 'orq.pop', clearProps: 'all' }, tNodo(r) + Math.min(k, 6) * 0.045)
    }
    if (seq.value) tl.fromTo(q('.ll'), { opacity: 0 }, { opacity: 1, duration: 0.6, stagger: 0.05, ease: 'power1.out', clearProps: 'opacity' }, 0.2)
    for (const g of q('.ar')) {
      const r = Number(g.dataset.r ?? 0)
      const t0 = seq.value ? 0.45 + r * paso : tNodo(r) + 0.3
      const ln = g.querySelector<SVGPathElement>('.ln')
      const dash = g.classList.contains('tr-respuesta') || g.classList.contains('tr-datos')
      if (ln && ln.getAttribute('d')) {
        if (dash) tl.fromTo(ln, { opacity: 0 }, { opacity: 1, duration: 0.5, ease: 'power1.out', clearProps: 'opacity' }, t0)
        else {
          tl.set(ln, { opacity: 1 }, t0)
          tl.fromTo(ln, { drawSVG: '0%' }, { drawSVG: '100%', duration: 0.55, ease: 'power2.inOut', clearProps: 'stroke-dasharray,stroke-dashoffset,opacity' }, t0)
        }
      }
      const fin = t0 + (ln?.getAttribute('d') ? 0.45 : 0)
      const pt = g.querySelector('.pt')
      if (pt) tl.fromTo(pt, { opacity: 0, scale: 0.3, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.35, ease: 'back.out(2)', clearProps: 'all' }, fin)
      const et = g.querySelector('.et')
      if (et) tl.fromTo(et, { opacity: 0, y: 4 }, { opacity: 1, y: 0, duration: 0.4, ease: 'power2.out', clearProps: 'all' }, fin - 0.1)
      const num = g.querySelector('.num')
      if (num) tl.fromTo(num, { opacity: 0, scale: 0.4, transformOrigin: '50% 50%' }, { opacity: 1, scale: 1, duration: 0.45, ease: 'orq.pop', clearProps: 'all' }, t0 - 0.05)
    }
    return tl
  }))
}

const dot = ref<SVGCircleElement | null>(null)
let ciclo: gsap.core.Tween | null = null
let viajando: gsap.core.Tween | null = null

/** Every few seconds a small light runs along one solid line, so the diagram feels alive without getting busy. */
function pulsar(on: boolean) {
  ciclo?.kill()
  ciclo = null
  if (!on) {
    viajando?.kill()
    viajando = null
    if (dot.value) gsap.set(dot.value, { opacity: 0 })
    return
  }
  const siguiente = (espera: number) => {
    ciclo = gsap.delayedCall(espera, () => {
      const el = dot.value
      const cands = q('.ar:not(.tr-respuesta):not(.tr-datos):not(.dim) .ln').filter((p) => p.getAttribute('d'))
      if (el && cands.length && !document.hidden) {
        const p = cands[Math.floor(Math.random() * cands.length)] as SVGPathElement
        viajando = run(() =>
          gsap
            .timeline()
            .set(el, { opacity: 0 })
            .to(el, { opacity: 1, duration: 0.25 }, 0)
            .to(el, { motionPath: { path: p, align: p, alignOrigin: [0.5, 0.5] }, duration: Math.min(1.6, 0.6 + p.getTotalLength() / 260), ease: 'power1.inOut' }, 0)
            .to(el, { opacity: 0, duration: 0.3 }, '>-0.25'),
        ) as unknown as gsap.core.Tween
      }
      siguiente(2.6 + Math.random() * 3.2)
    })
  }
  siguiente(1.2)
}
onBeforeUnmount(() => pulsar(false))

defineExpose({ entrar, ocultar, mostrar, pulsar, svg })
</script>

<template>
  <svg
    ref="svg"
    class="dg"
    :class="{ seq, hayfoco: !!foco, estatico }"
    :viewBox="`0 0 ${escena.w} ${escena.h}`"
    :width="ancho ?? escena.w"
    :height="alto ?? escena.h"
    role="img"
    :aria-label="titulo || 'Diagrama'"
    @click="tocar(null)"
  >
    <defs>
      <filter :id="`${uid}-sh`" x="-20%" y="-20%" width="140%" height="160%">
        <feDropShadow dx="0" dy="3" stdDeviation="4" flood-color="#000" flood-opacity="0.16" />
      </filter>
    </defs>

    <g v-for="g in escena.grupos" :key="g.key" class="gr" :class="[`g-${g.color}`, { dim: !!foco }]">
      <rect :x="g.x" :y="g.y" :width="g.w" :height="g.h" rx="18" class="gr-box" />
      <circle :cx="g.x + 16" :cy="g.y + 14" r="3.5" class="gr-dot" />
      <text :x="g.x + 26" :y="g.y + 18" class="gr-tx">{{ g.nombre }}</text>
    </g>

    <line v-for="l in escena.lineas" :key="`l${l.key}`" class="ll" :class="{ dim: apagado(l.key), lit: encendido(l.key) }" :x1="l.x" :x2="l.x" :y1="l.y1" :y2="l.y2" />

    <g
      v-for="{ a, et } in aristas"
      :key="a.key"
      class="ar"
      :class="clsA(a)"
      :data-r="a.rank"
      :data-k="a.key"
      @click.stop="a.propia ? tocar(a.key) : tocar(null)"
      @pointerenter="a.propia && sobre(a.key)"
      @pointerleave="a.propia && sobre(null)"
    >
      <path v-if="a.d && a.propia" class="hit" :d="a.d" />
      <path v-if="a.d" class="ln" :d="a.d" />
      <path v-if="a.punta" class="pt" :d="a.punta" />
      <g v-if="a.etiqueta" class="et" :class="{ ev: a.trazo === 'evento' || !a.d, plain: seq && !!a.d }">
        <rect :x="a.etiqueta.x" :y="a.etiqueta.y" :width="a.etiqueta.w" :height="a.etiqueta.h" :rx="a.d ? 7 : 10" class="et-box" />
        <text class="et-tx">
          <tspan v-for="(l, i) in et" :key="i" :x="a.etiqueta.x + a.etiqueta.w / 2" :y="l.y">{{ l.t }}</tspan>
        </text>
      </g>
      <g v-if="a.num && a.numPos" class="num">
        <circle :cx="a.numPos.x" :cy="a.numPos.y" r="10" />
        <text :x="a.numPos.x" :y="a.numPos.y + 3.6">{{ a.num }}</text>
      </g>
    </g>

    <g v-for="p in nodos" :key="p.n.key" :transform="`translate(${p.n.x},${p.n.y})`" class="nd-pos">
      <g
        class="nd-in"
        :class="[`f-${p.forma}`, `t-${p.n.tono}`, { dim: apagado(p.n.key), lit: encendido(p.n.key), sel: sel === p.n.key }]"
        :data-r="p.n.rank"
        :data-k="p.n.key"
        @click.stop="tocar(p.n.key)"
        @pointerenter="sobre(p.n.key)"
        @pointerleave="sobre(null)"
      >
        <path class="nd-halo" :d="p.d" />
        <path class="nd-box" :d="p.d" :filter="`url(#${uid}-sh)`" />
        <path v-if="p.extra" class="nd-extra" :d="p.extra" />
        <g v-if="p.icon">
          <rect :x="p.icon.x" :y="p.icon.y" width="26" height="26" rx="8" class="nd-chip" />
          <text :x="p.icon.x + 13" :y="p.icon.y + 18" class="nd-emo">{{ p.n.icono }}</text>
        </g>
        <text class="nd-tx" :style="{ fontSize: `${p.px}px`, fontWeight: p.peso }">
          <tspan v-for="(l, i) in p.n.lineas" :key="i" :x="p.tx" :y="p.ty[i]">{{ l }}</tspan>
        </text>
        <text v-if="p.n.sub" class="nd-sub" :x="p.tx" :y="p.subY">{{ p.n.sub }}</text>
        <g v-if="p.n.num" class="nd-num">
          <circle cx="2" cy="2" r="9.5" />
          <text x="2" y="5.6">{{ p.n.num }}</text>
        </g>
      </g>
    </g>

    <circle ref="dot" class="dot" r="3.4" cx="0" cy="0" opacity="0" />
  </svg>
</template>

<style scoped>
.dg {
  display: block;
  overflow: visible;
  font-family: var(--font-ui);
  user-select: none;
  -webkit-user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.dg text {
  font-family: var(--font-ui);
}

/* groups */
.gr {
  --gc: var(--text-3);
  transition: opacity 0.3s;
}
.g-verde { --gc: var(--st-done); }
.g-azul { --gc: var(--ansi-4); }
.g-ambar { --gc: var(--st-blocked); }
.g-rojo { --gc: var(--danger); }
.g-violeta { --gc: var(--ansi-5); }
.g-gris { --gc: var(--text-3); }
.g-lima { --gc: var(--accent); }
.g-rosa { --gc: var(--ansi-13); }
.gr-box {
  fill: color-mix(in srgb, var(--gc) 6%, transparent);
  stroke: color-mix(in srgb, var(--gc) 34%, transparent);
  stroke-width: 1;
}
.gr-dot {
  fill: var(--gc);
}
.gr-tx {
  font-size: var(--t-xs);
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  fill: color-mix(in srgb, var(--gc) 72%, var(--text));
}
.gr.dim {
  opacity: 0.55;
}

/* lifelines */
.ll {
  stroke: var(--line-2);
  stroke-width: 1.4;
  stroke-dasharray: 3 5;
  stroke-linecap: round;
  transition: opacity 0.3s, stroke 0.3s;
}
.ll.lit {
  stroke: color-mix(in srgb, var(--accent) 60%, transparent);
}
.ll.dim {
  opacity: 0.45;
}

/* edges */
.ar {
  --ec: color-mix(in srgb, var(--text) 40%, transparent);
  transition: opacity 0.3s;
}
.tr-datos { --ec: color-mix(in srgb, var(--ansi-5) 80%, transparent); }
.tr-error { --ec: var(--danger); }
.tr-si { --ec: var(--st-done); }
.tr-no { --ec: color-mix(in srgb, var(--danger) 85%, transparent); }
.ln {
  fill: none;
  stroke: var(--ec);
  stroke-width: 1.6;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: stroke 0.3s, stroke-width 0.3s;
}
.tr-respuesta .ln { stroke-dasharray: 6 5; }
.tr-datos .ln { stroke-dasharray: 1.5 5; stroke-width: 2.2; }
.pt {
  fill: var(--ec);
  stroke: var(--ec);
  stroke-width: 1;
  stroke-linejoin: round;
  transition: fill 0.3s, stroke 0.3s;
}
.hit {
  fill: none;
  stroke: transparent;
  stroke-width: 18;
  pointer-events: stroke;
}
.ar.lit {
  --ec: var(--accent);
}
.ar.lit.tr-error,
.ar.lit.tr-no { --ec: var(--danger); }
.ar.lit.tr-si { --ec: var(--st-done); }
.ar.lit .ln {
  stroke-width: 2.4;
}
.ar.dim {
  opacity: 0.16;
}
.et-box {
  fill: var(--surface);
  stroke: var(--line-2);
  stroke-width: 1;
}
.et.plain .et-box {
  fill: var(--surface);
  stroke: none;
  opacity: 0.88;
}
.et.ev .et-box {
  fill: color-mix(in srgb, var(--accent) 9%, var(--surface));
  stroke: color-mix(in srgb, var(--accent) 45%, transparent);
}
.tr-error .et.ev .et-box {
  fill: color-mix(in srgb, var(--danger) 10%, var(--surface));
  stroke: color-mix(in srgb, var(--danger) 50%, transparent);
}
.et-tx {
  font-size: var(--t-sm);
  font-weight: 500;
  text-anchor: middle;
  fill: var(--text-2);
}
.tr-si .et-tx,
.tr-no .et-tx {
  font-weight: 700;
  fill: var(--ec);
}
.tr-error .et-tx { fill: var(--danger); }
.et.ev .et-tx { fill: var(--text); }
.ar.lit .et-box {
  stroke: color-mix(in srgb, var(--ec) 70%, transparent);
}
.ar.lit .et-tx {
  fill: var(--text);
}
.num circle {
  fill: var(--surface-2);
  stroke: var(--line-2);
}
.num text {
  font-size: var(--t-xs);
  font-weight: 700;
  text-anchor: middle;
  fill: var(--text-2);
  font-variant-numeric: tabular-nums;
}
.ar.lit .num circle {
  fill: var(--accent);
  stroke: var(--accent);
}
.ar.lit .num text {
  fill: var(--accent-ink);
}
.propia {
  cursor: pointer;
}

/* nodes */
.nd-in {
  --c: var(--text-3);
  cursor: pointer;
  transition: opacity 0.3s;
}
.t-acento { --c: var(--accent); }
.t-cian { --c: var(--st-working); }
.t-verde { --c: var(--st-done); }
.t-ambar { --c: var(--st-blocked); }
.t-violeta { --c: var(--ansi-5); }
.t-rojo { --c: var(--danger); }
.t-gris { --c: var(--text-4); }
.t-neutro { --c: var(--text-3); }
.t-amarillo { --c: var(--ansi-3); }
.nd-box {
  fill: color-mix(in srgb, var(--c) 11%, var(--surface));
  stroke: color-mix(in srgb, var(--c) 52%, transparent);
  stroke-width: 1.2;
  stroke-linejoin: round;
  transition: stroke 0.3s, stroke-width 0.3s, fill 0.3s;
}
.t-neutro .nd-box {
  fill: var(--surface-2);
  stroke: var(--line-2);
}
.f-externo .nd-box {
  fill: var(--surface);
  stroke-dasharray: 5 4;
}
.f-nota .nd-box {
  fill: color-mix(in srgb, var(--c) 14%, var(--surface));
}
.f-terminal.t-acento .nd-box {
  fill: var(--accent);
  stroke: var(--accent);
}
.f-terminal.t-acento .nd-tx {
  fill: var(--accent-ink);
}
.f-terminal.t-gris .nd-box {
  fill: var(--surface-2);
  stroke: var(--line-2);
}
.f-actor .nd-box {
  fill: color-mix(in srgb, var(--accent) 8%, var(--surface-2));
  stroke: color-mix(in srgb, var(--accent) 34%, var(--line-2));
}
.nd-extra {
  fill: none;
  stroke: color-mix(in srgb, var(--c) 52%, transparent);
  stroke-width: 1.2;
}
.nd-halo {
  fill: none;
  stroke: var(--accent);
  stroke-width: 7;
  stroke-linejoin: round;
  opacity: 0;
  transition: opacity 0.3s;
}
.nd-chip {
  fill: color-mix(in srgb, var(--c) 18%, transparent);
}
.nd-emo {
  font-size: 15px;
  text-anchor: middle;
}
.nd-tx {
  text-anchor: middle;
  fill: var(--text);
  letter-spacing: -0.005em;
}
.f-terminal.t-gris .nd-tx {
  fill: var(--text-2);
}
.nd-sub {
  font-size: 11px;
  font-weight: 500;
  text-anchor: middle;
  fill: var(--text-3);
}
.nd-num circle {
  fill: var(--surface);
  stroke: color-mix(in srgb, var(--c) 60%, var(--line-2));
  stroke-width: 1.2;
}
.nd-num text {
  font-size: var(--t-xs);
  font-weight: 700;
  text-anchor: middle;
  fill: var(--text-2);
  font-variant-numeric: tabular-nums;
}
.nd-in.lit .nd-box {
  stroke: var(--accent);
  stroke-width: 1.8;
}
.nd-in.lit .nd-num circle {
  fill: var(--accent);
  stroke: var(--accent);
}
.nd-in.lit .nd-num text {
  fill: var(--accent-ink);
}
.nd-in.sel .nd-halo {
  opacity: 0.22;
}
.nd-in.dim {
  opacity: 0.3;
}
@media (hover: hover) {
  .dg:not(.hayfoco):not(.estatico) .nd-in:hover .nd-box {
    stroke: color-mix(in srgb, var(--accent) 70%, transparent);
  }
}
.estatico .nd-in,
.estatico .propia {
  cursor: default;
}

.dot {
  fill: var(--accent);
  pointer-events: none;
  filter: drop-shadow(0 0 4px var(--accent));
}
</style>

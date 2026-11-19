<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { actoresEnOrden, ramas, resumenPasos, ruta, type DiagramaPasos, type Rama } from '../lib/pasos'
import { gsap, useGsap } from '../motion'

const props = defineProps<{ diagrama: DiagramaPasos; activo: number; playing: boolean }>()
const emit = defineEmits<{ elegir: [a: number]; reiniciar: [] }>()

const { run } = useGsap()
const capas = ref<HTMLElement[]>([])
const rec = ref<HTMLElement | null>(null)
const altoMax = ref(0)
let animando = false

const seq = computed(() => props.diagrama.tipo === 'secuencia')
const fin = computed(() => props.diagrama.pasos.length)
const resumen = computed(() => resumenPasos(props.diagrama))
const orden = computed(() => (seq.value ? actoresEnOrden(props.diagrama) : []))
const largo = computed(() => ruta(props.diagrama).length)
const decisiones = computed(() => props.diagrama.pasos.map((_, i) => ramas(props.diagrama, i)))
const icono = (a: number) => props.diagrama.actores[a].icono || props.diagrama.actores[a].nombre.slice(0, 1).toUpperCase()
const nombre = (a: number) => props.diagrama.actores[a].nombre
const etiqueta = (i: number) => {
  const at = ruta(props.diagrama).indexOf(i)
  return at >= 0 ? `Paso ${at + 1} de ${largo.value}` : 'Rama alternativa'
}
const TIPO: Record<string, string> = { llamada: 'Llamada', respuesta: 'Respuesta', evento: 'Evento', error: 'Error' }
const siActivo = (r: Rama | null) => !!r && props.playing

function limpiar(el: HTMLElement) {
  gsap.killTweensOf(el)
  gsap.killTweensOf(el.querySelectorAll('[data-a]'))
  gsap.set([el, ...el.querySelectorAll('[data-a]')], { clearProps: 'all' })
}

/** Natural height of a layer plus the box padding, capped by the box's max-height. */
function altoDe(i: number): number {
  const c = capas.value[i]
  const el = rec.value
  if (!c || !el) return 0
  const cs = getComputedStyle(el)
  const tope = parseFloat(cs.maxHeight)
  const h = c.offsetHeight + parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom)
  return Number.isFinite(tope) ? Math.min(h, tope) : h
}

/** Sets the box height to the active layer's content right away. */
function ajustar(i = props.activo) {
  const el = rec.value
  if (!el) return
  altoMax.value = Math.max(0, ...capas.value.map((_, k) => altoDe(k)))
  if (animando) return
  const h = altoDe(i)
  if (h > 0) el.style.height = `${h}px`
}

/** Swaps the content: the old layer leaves toward the side it came from, the new one arrives from the direction of travel. */
function entrar(from: number | undefined, to: number, soft: boolean): gsap.core.Timeline {
  return run(() => {
    const tl = gsap.timeline()
    const nuevo = capas.value[to]
    const viejo = from !== undefined && from !== to ? capas.value[from] : undefined
    capas.value.forEach((c) => c !== nuevo && c !== viejo && limpiar(c))
    if (!nuevo) return tl
    limpiar(nuevo)
    if (viejo) limpiar(viejo)
    const el = rec.value
    const h = altoDe(to)
    if (el && h > 0) {
      if (soft || from === undefined) {
        gsap.killTweensOf(el)
        animando = false
        el.style.height = `${h}px`
      } else {
        el.style.height = `${el.offsetHeight}px`
        animando = true
        tl.to(el, { height: h, duration: 0.42, ease: 'power3.inOut', onComplete: () => { animando = false }, onInterrupt: () => { animando = false } }, 0)
      }
    }
    const dir = from === undefined || to >= from ? 1 : -1
    if (soft || from === undefined) {
      tl.fromTo(nuevo, { autoAlpha: 0 }, { autoAlpha: 1, duration: soft ? 0.25 : 0.4, ease: 'power2.out', clearProps: 'all' })
      return tl
    }
    if (viejo) {
      gsap.set(viejo, { autoAlpha: 1 })
      tl.to(viejo, { autoAlpha: 0, x: -dir * 26, duration: 0.28, ease: 'power2.in', onComplete: () => limpiar(viejo) }, 0)
    }
    tl.fromTo(nuevo, { autoAlpha: 0, x: dir * 34 }, { autoAlpha: 1, x: 0, duration: 0.5, ease: 'power3.out', clearProps: 'all' }, 0.12)
    const partes = nuevo.querySelectorAll('[data-a]')
    tl.fromTo(partes, { autoAlpha: 0, y: 10 }, { autoAlpha: 1, y: 0, duration: 0.45, stagger: 0.06, ease: 'power3.out', clearProps: 'all' }, 0.2)
    return tl
  })
}

function reveal() {
  run(() => {
    capas.value.forEach(limpiar)
    if (rec.value) gsap.killTweensOf(rec.value)
    animando = false
    ajustar()
  })
}

let ro: ResizeObserver | null = null
onMounted(() => {
  reveal()
  ro = new ResizeObserver(() => ajustar())
  capas.value.forEach((c) => ro!.observe(c))
  document.fonts?.ready.then(() => ajustar())
})
onBeforeUnmount(() => ro?.disconnect())
defineExpose({ entrar, reveal, altoMax })
</script>

<template>
  <div ref="rec" class="rec" :class="{ seq }">
    <article
      v-for="(p, i) in diagrama.pasos"
      :key="i"
      :ref="(el) => (capas[i] = el as HTMLElement)"
      class="capa"
      :class="{ on: i === activo }"
      :inert="i !== activo"
    >
      <div class="top" data-a>
        <span class="num mono">{{ etiqueta(i) }}</span>
        <span v-if="p.decision" class="tag">Decisión</span>
        <span v-else-if="seq" class="tag" :class="p.tipo">{{ TIPO[p.tipo] }}</span>
      </div>
      <div v-if="seq" class="quien" data-a>
        <span class="act"><i>{{ icono(p.de) }}</i>{{ nombre(p.de) }}</span>
        <template v-if="p.de !== p.a">
          <b class="ar">→</b>
          <span class="act"><i>{{ icono(p.a) }}</i>{{ nombre(p.a) }}</span>
        </template>
      </div>
      <p class="tx" data-a>{{ p.texto }}</p>
      <p v-if="p.detalle" class="dt" data-a>{{ p.detalle }}</p>
      <p v-if="p.datos" class="datos mono" data-a>{{ p.datos }}</p>
      <p v-if="p.duracion" class="dur mono" data-a>{{ p.duracion }}</p>
      <div v-if="decisiones[i]" class="dec" data-a>
        <p class="q">{{ decisiones[i]!.pregunta }}</p>
        <div class="ans">
          <div v-for="k in (['si', 'no'] as const)" :key="k" class="opt" :class="[k, { back: decisiones[i]![k]?.vuelve }]">
            <button type="button" class="b" :class="{ auto: k === 'si' && siActivo(decisiones[i]![k]) }" :disabled="i !== activo || !decisiones[i]![k]" @click="emit('elegir', decisiones[i]![k]!.a)">
              {{ k === 'si' ? 'Sí' : 'No' }}
            </button>
            <span class="av">{{ decisiones[i]![k] ? `${decisiones[i]![k]!.vuelve ? 'Volvés al' : 'Seguís en el'} paso ${decisiones[i]![k]!.numero}` : 'Termina acá' }}</span>
          </div>
        </div>
      </div>
    </article>

    <article :ref="(el) => (capas[fin] = el as HTMLElement)" class="capa fin" :class="{ on: activo === fin }" :inert="activo !== fin">
      <div class="top" data-a><span class="num mono">Resumen</span></div>
      <p class="tx fin-tx" data-a><template v-for="(t, k) in resumen.linea.split(' · ')" :key="k"><template v-if="k"> · </template><span class="nw">{{ t }}</span></template></p>
      <div v-if="orden.length" class="quien" data-a>
        <template v-for="(a, k) in orden" :key="a">
          <b v-if="k" class="ar">→</b>
          <span class="act"><i>{{ icono(a) }}</i>{{ nombre(a) }}</span>
        </template>
      </div>
      <ul v-if="diagrama.notas.length" class="notas" data-a>
        <li v-for="(n, i) in diagrama.notas" :key="i">{{ n }}</li>
      </ul>
      <button type="button" class="otra" data-a @click="emit('reiniciar')">Volver a empezar</button>
    </article>
  </div>
</template>

<style scoped>
.rec {
  position: relative;
  min-width: 0;
  max-height: var(--rec-max, 260px);
  padding: 14px 16px 16px;
  border-radius: 16px;
  background: linear-gradient(160deg, var(--surface-2), var(--surface));
  box-shadow: inset 0 0 0 1px var(--line-2), 0 14px 34px -22px rgba(0, 0, 0, 0.55);
  overflow: hidden;
  touch-action: pan-y;
  user-select: none;
  -webkit-user-select: none;
}
.capa {
  position: absolute;
  top: 14px;
  left: 16px;
  right: 16px;
  max-height: calc(var(--rec-max, 260px) - 30px);
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 6px;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: none;
  visibility: hidden;
  opacity: 0;
}
.capa.on {
  visibility: visible;
  opacity: 1;
}
.top {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 100%;
}
.num {
  font-size: var(--t-sm);
  font-weight: 600;
  color: var(--accent);
}
.tag {
  padding: 1px 8px;
  border-radius: 8px;
  font-size: 11px;
  font-weight: 700;
  color: var(--st-working);
  background: var(--st-working-soft);
}
.tag.llamada { color: var(--accent); background: var(--accent-soft); }
.tag.respuesta { color: var(--st-working); background: var(--st-working-soft); }
.tag.evento { color: var(--st-done); background: var(--st-done-soft); }
.tag.error { color: var(--danger); background: var(--danger-soft); }
.quien {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
}
.act {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 9px 2px 3px;
  border-radius: var(--r-lg);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line);
}
.act i {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  font-style: normal;
  font-size: 14px;
  line-height: 1;
}
.ar {
  color: var(--text-3);
}
.tx {
  margin: 0;
  font-family: var(--font-display);
  font-size: var(--tx, 20px);
  font-weight: 600;
  line-height: 1.22;
  letter-spacing: -0.012em;
  text-wrap: balance;
  overflow-wrap: anywhere;
}
.fin-tx { font-size: calc(var(--tx, 20px) - 3px); }
.nw { white-space: nowrap; }
.dt {
  margin: 0;
  font-size: var(--dt, 14px);
  line-height: 1.48;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.datos {
  margin: 0;
  padding: 5px 9px;
  max-width: 100%;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.4;
  background: var(--code-bg);
  color: #c9ccc2;
  overflow-wrap: anywhere;
}
.dur {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  color: var(--st-blocked);
}
.dur::before {
  content: '⏱ ';
}
.dec {
  display: grid;
  gap: 8px;
  width: 100%;
  margin-top: 2px;
}
.q {
  margin: 0;
  font-size: calc(var(--dt, 14px) + 1px);
  font-weight: 600;
  color: var(--st-working);
}
.ans {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}
.opt {
  display: grid;
  gap: 4px;
  min-width: 0;
}
.b {
  height: var(--bh, 38px);
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
  transition: scale 0.3s var(--spring), background 0.2s, opacity 0.2s;
}
.opt.no .b {
  color: var(--st-blocked);
  background: var(--st-blocked-soft);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--st-blocked) 55%, transparent);
}
.b:disabled {
  opacity: 0.4;
  cursor: default;
}
.b:not(:disabled):active {
  scale: var(--press-scale);
}
.b.auto {
  animation: fl-auto 1.4s ease-in-out infinite;
}
:root[data-motion='soft'] .b.auto { animation: none; }
@keyframes fl-auto {
  50% { box-shadow: inset 0 0 0 1px var(--accent-line), 0 0 14px -2px var(--accent); }
}
@media (hover: hover) {
  .b:not(:disabled):hover { background: color-mix(in srgb, var(--accent) 20%, transparent); }
}
.av {
  font-size: var(--t-sm);
  line-height: 1.3;
  text-align: center;
  color: var(--text-3);
}
.notas {
  margin: 0;
  padding-left: 18px;
  display: grid;
  gap: 6px;
  font-size: var(--dt, 14px);
  line-height: 1.45;
  color: var(--text-2);
}
.otra {
  margin-top: 2px;
  height: 36px;
  padding: 0 14px;
  border-radius: 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
}
@media (hover: hover) {
  .otra:hover { color: var(--text); background: var(--surface-hover); }
}
</style>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { getUsoLimites } from '../api/usoPlanApi'
import { faltaPara, horaLocal, nivel, textoCorto, ariaPlan, ventanas, viejo, type UsoPlan } from '../lib/usoPlan'
import { ago, useNow } from '../lib/time'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'

const props = defineProps<{ compact?: boolean; cargar?: () => Promise<UsoPlan | null> }>()

const REFRESCO_MS = 60_000
const plan = ref<UsoPlan | null>(null)
const abierto = ref(false)
const panel = ref<HTMLElement | null>(null)
const btn = ref<HTMLButtonElement | null>(null)
const cerrarBtn = ref<HTMLButtonElement | null>(null)
const now = useNow()
const ancha = ref(false)
const pos = ref({ top: 0, right: 0 })
const query = typeof window !== 'undefined' && window.matchMedia ? window.matchMedia('(min-width: 640px)') : null

function medir() {
  ancha.value = query?.matches ?? false
  const r = btn.value?.getBoundingClientRect()
  if (r) pos.value = { top: r.bottom + 10, right: Math.max(8, window.innerWidth - r.right - 4) }
}
function abrir() {
  medir()
  abierto.value = true
}

const lista = computed(() => (plan.value ? ventanas(plan.value) : []))
const texto = computed(() => (plan.value ? textoCorto(plan.value) : ''))
const aria = computed(() => (plan.value ? ariaPlan(plan.value) : ''))
const gris = computed(() => (plan.value ? viejo(plan.value, now.value) : false))
const hace = computed(() => ago(plan.value?.actualizado, now.value))
const filas = computed(() =>
  lista.value.map((v) => ({
    key: v.key,
    titulo: v.titulo,
    corto: v.corto,
    pct: Math.round(v.lim.pct),
    quedan: Math.max(0, 100 - Math.round(v.lim.pct)),
    vencido: v.lim.vencido,
    nivel: v.lim.vencido ? 'ok' : nivel(v.lim.pct),
    falta: faltaPara(v.lim.resetsAt, now.value),
    hora: horaLocal(v.lim.resetsAt),
  })),
)

const arco = (key: '5h' | '7d') => {
  const f = filas.value.find((x) => x.key === key)
  return f ? { nivel: f.nivel, pct: f.vencido ? 0 : f.pct } : null
}
const afuera = computed(() => arco('5h'))
const adentro = computed(() => arco('7d'))

let busy = false
async function refrescar() {
  if (busy || (typeof document !== 'undefined' && document.hidden)) return
  busy = true
  try {
    plan.value = await (props.cargar ?? getUsoLimites)()
  } catch {
    /* se queda con el último dato; la pastilla se pone gris sola si envejece */
  } finally {
    busy = false
  }
}

let timer: ReturnType<typeof setInterval> | undefined
function alVolver() {
  if (!document.hidden) void refrescar()
}
function alCambiar() {
  if (abierto.value) medir()
}
onMounted(() => {
  void refrescar()
  timer = setInterval(() => void refrescar(), REFRESCO_MS)
  document.addEventListener('visibilitychange', alVolver)
  window.addEventListener('resize', alCambiar)
})
onBeforeUnmount(() => {
  clearInterval(timer)
  document.removeEventListener('visibilitychange', alVolver)
  window.removeEventListener('resize', alCambiar)
})

function cerrar() {
  abierto.value = false
  btn.value?.focus()
}
watch(plan, (p) => {
  if (!p && abierto.value) cerrar()
})
const { onKeydown } = useFocusTrap(panel, abierto, { onEscape: cerrar, initial: () => cerrarBtn.value })
useSheetSwipe(panel, cerrar, { direccion: 'arriba', activo: () => !ancha.value })
</script>

<template>
  <div v-if="plan && lista.length" class="uso-plan" :class="{ compact, gris }">
    <button ref="btn" type="button" class="pill hit" :aria-label="aria" aria-haspopup="dialog" :aria-expanded="abierto" @click="abrir">
      <svg v-if="compact" class="mini" viewBox="0 0 22 22" width="22" height="22" aria-hidden="true">
        <circle class="track" cx="11" cy="11" r="9" pathLength="100" />
        <circle v-if="afuera" class="arc" :data-nivel="afuera.nivel" cx="11" cy="11" r="9" pathLength="100" :stroke-dasharray="`${afuera?.pct ?? 0} 100`" />
        <circle class="track" cx="11" cy="11" r="5" pathLength="100" />
        <circle v-if="adentro" class="arc" :data-nivel="adentro.nivel" cx="11" cy="11" r="5" pathLength="100" :stroke-dasharray="`${adentro?.pct ?? 0} 100`" />
      </svg>
      <template v-else>
        <span class="barras" aria-hidden="true">
          <i v-for="f in filas" :key="f.key" class="bar" :data-nivel="f.nivel"><b :style="{ width: `${f.vencido ? 0 : f.pct}%` }" /></i>
        </span>
        <span class="txt mono">{{ texto }}</span>
      </template>
    </button>

    <Teleport to="body">
      <Transition name="up">
        <div v-if="abierto" class="up-root" @keydown="onKeydown">
          <div class="up-scrim" @click="cerrar" />
          <div ref="panel" class="up" :class="ancha ? 'ancla' : 'arriba'" role="dialog" aria-modal="true" aria-labelledby="up-t" tabindex="-1" :style="ancha ? { top: `${pos.top}px`, right: `${pos.right}px` } : undefined">
            <h3 id="up-t" class="sheet-title">Plan de Claude</h3>
            <ul class="vent">
              <li v-for="f in filas" :key="f.key" class="v" :data-nivel="f.nivel">
                <div class="v-head">
                  <span class="v-t">{{ f.titulo }}</span>
                  <b class="mono v-pct">{{ f.vencido ? 'renovado' : `${f.pct}% usado` }}</b>
                </div>
                <i class="bar grande"><b :style="{ width: `${f.vencido ? 0 : f.pct}%` }" /></i>
                <p class="v-sub">
                  <template v-if="f.vencido">Ya se renovó; esperando el dato nuevo.</template>
                  <template v-else>
                    Quedan {{ f.quedan }}%<template v-if="f.falta"> · se renueva en {{ f.falta }}<template v-if="f.hora"> ({{ f.hora }})</template></template>
                  </template>
                </p>
              </li>
            </ul>
            <p class="act" :class="{ gris }">Actualizado {{ hace || 'hace un rato' }}<template v-if="gris"> · puede estar desfasado</template></p>
            <div class="sheet-actions">
              <button ref="cerrarBtn" type="button" class="btn btn-ghost" @click="cerrar">Cerrar</button>
            </div>
            <i class="sheet-grip" aria-hidden="true" />
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
.uso-plan { display: inline-flex; align-items: center; flex: none; }
.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 28px;
  padding: 0 9px;
  border-radius: var(--r-md);
  color: var(--text-2);
  font-size: var(--t-sm, 12px);
  transition: background 0.2s, color 0.2s, transform 0.2s var(--ease-out);
}
.pill:hover { background: var(--surface-hover); color: var(--text); }
.pill:active { transform: scale(var(--press-scale, 0.97)); }
.gris .pill { opacity: 0.55; }
.txt { white-space: nowrap; font-variant-numeric: tabular-nums; }
.barras { display: grid; gap: 3px; width: 34px; }
.bar { --c: var(--st-done); display: block; height: 3px; border-radius: 3px; background: var(--line-2); overflow: hidden; }
.bar[data-nivel='atento'], .v[data-nivel='atento'] .bar { --c: var(--st-blocked); }
.bar[data-nivel='alto'], .v[data-nivel='alto'] .bar { --c: var(--danger); }
.bar b { display: block; height: 100%; border-radius: inherit; background: var(--c); transition: width 0.6s var(--ease-out); }
.bar.grande { height: 6px; border-radius: 6px; }
.compact .pill { width: 30px; height: 30px; padding: 0; justify-content: center; }
@media (max-width: 440px) {
  .uso-plan { min-width: 0; }
  .compact .pill { width: 26px; }
}
.mini { display: block; transform: rotate(-90deg); }
.mini circle { fill: none; stroke-width: 2.4; }
.mini .track { stroke: var(--line-2); }
.mini .arc { stroke: var(--st-done); stroke-linecap: round; transition: stroke-dasharray 0.6s var(--ease-out); }
.mini .arc[data-nivel='atento'] { stroke: var(--st-blocked); }
.mini .arc[data-nivel='alto'] { stroke: var(--danger); }

.up { display: grid; gap: 14px; align-content: start; position: relative; background: var(--surface); border: 1px solid var(--line-2); box-shadow: var(--shadow-pop); outline: none; overflow-y: auto; overscroll-behavior: contain; }
.up-root { position: fixed; inset: 0; z-index: 90; display: flex; align-items: flex-start; justify-content: center; }
.up-scrim { position: absolute; inset: 0; background: var(--scrim); overscroll-behavior: contain; touch-action: none; }
.up .sheet-title { touch-action: none; }
.up .sheet-grip { margin: 0 auto; }
.up.arriba { width: 100%; max-height: 86dvh; border-radius: 0 0 20px 20px; border-top: 0; padding: max(10px, env(safe-area-inset-top)) 18px 10px; }
.up.ancla { position: fixed; width: 340px; max-height: min(72vh, 640px); border-radius: 16px; padding: 18px 20px; transform-origin: top right; }
@media (min-width: 640px) {
  .up-scrim { background: transparent; }
}
.vent { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.v { display: grid; gap: 6px; }
.v-head { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
.v-t { font-size: 14px; color: var(--text-2); }
.v-pct { font-size: 14px; color: var(--text); }
.v-sub, .act { margin: 0; font-size: 13px; line-height: 1.45; color: var(--text-3); }
.act.gris { color: var(--text-4); }
.up-enter-active { transition: opacity 0.22s; }
.up-enter-active .up.arriba { transition: transform 0.42s var(--ease-sheet); }
.up-enter-active .up.ancla { transition: transform 0.2s var(--ease-out); }
.up-leave-active { transition: opacity 0.18s; }
.up-leave-active .up.arriba { transition: transform 0.3s var(--ease-sheet); }
.up-enter-from, .up-leave-to { opacity: 0; }
.up-enter-from .up.arriba, .up-leave-to .up.arriba { transform: translateY(-100%); }
.up-enter-from .up.ancla { transform: scale(0.96); }
/* Modo suave (toggle o SO: data-motion lo refleja, igual que isSoft()): solo fundido */
:root[data-motion='soft'] .up-enter-active .up.arriba,
:root[data-motion='soft'] .up-enter-active .up.ancla,
:root[data-motion='soft'] .up-leave-active .up.arriba { transition: none; }
:root[data-motion='soft'] .up-enter-from .up.arriba,
:root[data-motion='soft'] .up-leave-to .up.arriba,
:root[data-motion='soft'] .up-enter-from .up.ancla { transform: none; }
@media (prefers-reduced-motion: reduce) {
  .up-enter-active .up.arriba, .up-enter-active .up.ancla, .up-leave-active .up.arriba { transition: none; }
  .up-enter-from .up.arriba, .up-leave-to .up.arriba, .up-enter-from .up.ancla { transform: none; }
}
</style>

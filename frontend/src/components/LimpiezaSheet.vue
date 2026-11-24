<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { useSheetSwipe } from '../lib/useSheetSwipe'
import type { LimpiezaItem } from '../api/types'
import { agrupar, bloqueoLabel, itemKey, razonIcon, razonLabel, DIAS_MAX, DIAS_MIN } from '../lib/limpieza'
import { desktop } from '../lib/viewport'
import { gsap, isSoft, useGsap } from '../motion'
import {
  accionLimpieza,
  cerrarHoja,
  confirmar,
  fallidas,
  lm,
  marcadas,
  reintentar,
  resultadoDe,
  revisadas,
  revisar,
  setDias,
  toggleMarca,
  volverAElegir,
} from '../state/limpieza'
import ClosePaneList from './ClosePaneList.vue'
import GuardandoLote from './GuardandoLote.vue'
import HoldButton from './HoldButton.vue'
import Icon from './Icon.vue'

const { run } = useGsap()
const panel = ref<HTMLElement | null>(null)
const cancelBtn = ref<HTMLButtonElement | null>(null)
const volverBtn = ref<HTMLButtonElement | null>(null)
const body = ref<HTMLElement | null>(null)
const verAbierto = ref<Record<string, boolean>>({})

const agrupado = computed(() => agrupar(lm.items))
const nMarcadas = computed(() => marcadas.value.length)
const nRevisadas = computed(() => revisadas.value.length)
const itemsRevision = computed(() => lm.items.filter((i) => lm.previews[itemKey(i)]))
const itemsFin = computed(() => lm.items.filter((i) => resultadoDe(i)))
const titulo = computed(() =>
  lm.paso === 'elegir' ? 'Limpiar sesiones' : lm.paso === 'revisar' ? 'Revisá antes de cerrar' : lm.paso === 'cerrando' ? 'Cerrando…' : 'Listo',
)
const resumenFin = computed(() => {
  const c = lm.cerrados
  const k = lm.salteados
  const a = c === 1 ? 'Cerré 1' : `Cerré ${c}`
  if (!k) return a
  return `${a} · ${k === 1 ? '1 quedó abierta' : `${k} quedaron abiertas`}`
})
const nota = computed(() =>
  lm.git === 'ok' ? 'Ramas mergeadas según lo último que bajaste de git' : lm.git === 'parcial' ? 'No pude mirar git en algunas carpetas: puede faltar alguna mergeada' : 'No pude mirar git: solo cuento la inactividad',
)

const sesionLinea = (i: LimpiezaItem) => i.sesiones.map((s) => s.titulo).filter(Boolean).join(' · ')
const pendiente = (i: LimpiezaItem) => i.sesiones.map((s) => s.pendiente).find(Boolean) ?? ''
const toggleVer = (i: LimpiezaItem) => (verAbierto.value = { ...verAbierto.value, [itemKey(i)]: !verAbierto.value[itemKey(i)] })

const { onKeydown } = useFocusTrap(panel, () => lm.open, {
  onEscape: cerrarHoja,
  initial: () => cancelBtn.value ?? volverBtn.value ?? panel.value,
})
useSheetSwipe(panel, cerrarHoja)
watch(
  () => lm.open,
  (on) => {
    if (!on) verAbierto.value = {}
  },
)

watch(
  () => lm.tick,
  async () => {
    await nextTick()
    if (!body.value || isSoft()) return
    run(() => gsap.from(body.value!.querySelectorAll('.stag'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.04 }))
  },
)

const side = () => desktop.value
function onEnter(el: Element, done: () => void) {
  const back = el.querySelector('.sheet-scrim')
  const card = el.querySelector('.ls-panel')
  if (isSoft()) {
    run(() => gsap.fromTo(el, { opacity: 0 }, { opacity: 1, duration: 0.2, onComplete: done }))
    return
  }
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.fromTo(back, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'power2.out' }, 0)
    if (side()) tl.fromTo(card, { xPercent: 100 }, { xPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    else tl.fromTo(card, { yPercent: 100 }, { yPercent: 0, duration: 0.6, ease: 'expo.out' }, 0)
    tl.from(el.querySelectorAll('.stag'), { y: 10, opacity: 0, duration: 0.45, ease: 'power3.out', stagger: 0.04 }, 0.2)
  })
}
function onLeave(el: Element, done: () => void) {
  const card = el.querySelector('.ls-panel')
  if (isSoft()) {
    run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
    return
  }
  run(() => {
    const tl = gsap.timeline({ onComplete: done })
    tl.to(el.querySelector('.sheet-scrim'), { opacity: 0, duration: 0.22 }, 0)
    if (side()) tl.to(card, { xPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
    else tl.to(card, { yPercent: 100, duration: 0.3, ease: 'power3.in' }, 0)
  })
}

/** Una fila cerrada con éxito se pliega; en modo suave solo se atenúa. */
function onRowLeave(el: Element, done: () => void) {
  if (isSoft()) {
    run(() => gsap.to(el, { opacity: 0, duration: 0.15, onComplete: done }))
    return
  }
  run(() => gsap.to(el, { height: 0, opacity: 0, marginBottom: 0, paddingTop: 0, paddingBottom: 0, duration: 0.45, ease: 'power3.inOut', onComplete: done }))
}
const finVisibles = computed(() => itemsFin.value.filter((i) => !resultadoDe(i)!.ok || lm.paso !== 'fin'))
</script>

<template>
  <Teleport to="body">
    <Transition :css="false" @enter="onEnter" @leave="onLeave">
      <div v-if="lm.open" class="sheet-root ls" :class="{ side: desktop }" @keydown="onKeydown">
        <div class="sheet-scrim ls-back" @click="cerrarHoja" />
        <section ref="panel" class="sheet-panel ls-panel" role="dialog" aria-modal="true" aria-labelledby="ls-title" tabindex="-1" :data-paso="lm.paso">
          <header class="ls-head">
            <i class="sheet-grip grip" aria-hidden="true" />
            <div class="ls-top">
              <button v-if="lm.paso === 'revisar'" ref="volverBtn" type="button" class="back" aria-label="Volver a elegir" @click="volverAElegir">
                <Icon name="back" :size="16" />
              </button>
              <span v-else class="mark"><Icon name="broom" :size="16" /></span>
              <h2 id="ls-title" class="title">{{ titulo }}</h2>
              <button v-if="lm.paso !== 'cerrando'" type="button" class="x" aria-label="Cerrar" @click="cerrarHoja"><Icon name="close" :size="16" /></button>
            </div>
            <div v-if="lm.paso === 'elegir'" class="dias stag">
              <span class="dias-lbl">Quietas hace más de</span>
              <div class="stepper" role="group" aria-label="Días de inactividad">
                <button type="button" aria-label="Un día menos" :disabled="lm.dias <= DIAS_MIN" @click="setDias(lm.dias - 1)">−</button>
                <output :class="{ calc: lm.recalculando, 'sk-sweep': lm.recalculando }">{{ lm.dias }} {{ lm.dias === 1 ? 'día' : 'días' }}</output>
                <button type="button" aria-label="Un día más" :disabled="lm.dias >= DIAS_MAX" @click="setDias(lm.dias + 1)">+</button>
              </div>
            </div>
          </header>

          <div ref="body" class="ls-body">
            <p v-if="lm.aviso" class="aviso stag" role="alert"><Icon name="warn" :size="14" /> <span>{{ lm.aviso }}</span></p>

            <template v-if="lm.paso === 'elegir'">
              <p v-if="lm.error" class="aviso stag" role="alert"><Icon name="warn" :size="14" /> <span>{{ lm.error }}</span></p>
              <div v-if="!lm.loaded && !lm.error" class="skel" aria-busy="true"><i class="sk-sweep" /><i class="sk-sweep" /><i class="sk-sweep" /></div>
              <p v-else-if="lm.loaded && !lm.items.length" class="vacio stag">No hay sesiones quietas con ese criterio.</p>
              <div v-else class="lista" :class="{ calc: lm.recalculando, 'sk-sweep': lm.recalculando }">
                <section v-for="g in agrupado.grupos" :key="g.workspace" class="grupo stag">
                  <h3 class="g-name">{{ g.workspace }}</h3>
                  <div v-for="i in g.items" :key="itemKey(i)" class="fila" :class="{ on: lm.marcas[itemKey(i)] }">
                    <button
                      type="button"
                      class="check"
                      role="checkbox"
                      :aria-checked="!!lm.marcas[itemKey(i)]"
                      :aria-label="`Marcar ${i.label}`"
                      @click="toggleMarca(itemKey(i))"
                    >
                      <span class="box"><Icon name="check" :size="13" /></span>
                    </button>
                    <div class="f-main">
                      <div class="f-line">
                        <b class="f-label">{{ i.tipo === 'workspace' ? `Todo el workspace ${i.label}` : i.label }}</b>
                        <button v-if="i.sesiones.length" type="button" class="ver" :aria-expanded="!!verAbierto[itemKey(i)]" @click="toggleVer(i)">Ver</button>
                      </div>
                      <p v-if="sesionLinea(i)" class="f-ses">{{ sesionLinea(i) }}</p>
                      <p v-if="pendiente(i)" class="f-pend">{{ pendiente(i) }}</p>
                      <div class="chips">
                        <span v-for="r in i.razones" :key="r.tipo" class="chip" :data-r="r.tipo"><Icon :name="razonIcon(r)" :size="11" /> {{ razonLabel(r) }}</span>
                      </div>
                      <div v-if="verAbierto[itemKey(i)]" class="ver-box">
                        <p v-for="s in i.sesiones" :key="s.session_id"><b>{{ s.titulo || s.session_id }}</b><template v-if="s.pendiente"> · {{ s.pendiente }}</template></p>
                        <p class="ver-hint">Solo lectura: no se cierra nada desde acá.</p>
                      </div>
                    </div>
                  </div>
                </section>
                <section v-if="agrupado.bloqueados.length" class="grupo bloq stag">
                  <h3 class="g-name">No se pueden cerrar ahora</h3>
                  <div v-for="i in agrupado.bloqueados" :key="itemKey(i)" class="fila off">
                    <div class="f-main">
                      <b class="f-label">{{ i.label }}</b>
                      <p class="f-why"><Icon name="warn" :size="12" /> {{ bloqueoLabel(i.bloqueado!) }}</p>
                    </div>
                  </div>
                </section>
                <p class="nota stag">{{ nota }}</p>
              </div>
            </template>

            <template v-else-if="lm.paso === 'revisar'">
              <div v-if="lm.revisando" class="skel" aria-busy="true"><i class="sk-sweep" /><i class="sk-sweep" /></div>
              <template v-else>
                <section v-for="i in itemsRevision" :key="itemKey(i)" class="rev stag" :class="{ amber: !!lm.motivos[itemKey(i)] }">
                  <h3 class="g-name">{{ i.label }}</h3>
                  <p v-if="lm.motivos[itemKey(i)]" class="motivo"><Icon name="warn" :size="12" /> {{ lm.motivos[itemKey(i)] }} · lo desmarqué</p>
                  <ClosePaneList v-if="lm.previews[itemKey(i)].preview" :panes="lm.previews[itemKey(i)].preview!.panes" :bloqueantes="lm.previews[itemKey(i)].preview!.bloqueantes" />
                </section>
                <p class="nota stag">Las conversaciones de Claude quedan guardadas: se retoman con <code>claude --resume</code>. Lo que corre en las terminales se corta.</p>
              </template>
            </template>

            <template v-else>
              <TransitionGroup tag="div" class="cerr" :css="false" @leave="onRowLeave">
                <div v-for="i in finVisibles" :key="itemKey(i)" class="res" :class="{ ok: resultadoDe(i)!.ok, ko: !resultadoDe(i)!.ok }">
                  <span class="res-ico"><Icon :name="resultadoDe(i)!.ok ? 'check' : 'warn'" :size="14" /></span>
                  <div class="f-main">
                    <b class="f-label">{{ i.label }}</b>
                    <p v-if="!resultadoDe(i)!.ok" class="f-why">{{ resultadoDe(i)!.error }}</p>
                  </div>
                </div>
              </TransitionGroup>
              <GuardandoLote v-if="lm.paso === 'cerrando' && lm.lote" :lote="lm.lote" :ocupado="lm.accionando" @accion="accionLimpieza" />
              <p v-else-if="lm.paso === 'cerrando'" class="nota">Pidiendo que guarden antes de cerrar…</p>
              <p v-else class="resumen stag" role="status">{{ resumenFin }}</p>
            </template>
          </div>

          <footer class="ls-foot">
            <template v-if="lm.paso === 'elegir'">
              <button ref="cancelBtn" type="button" class="btn ghost" @click="cerrarHoja">Cancelar</button>
              <button type="button" class="btn primary" :disabled="!nMarcadas" @click="revisar">Revisar {{ nMarcadas || '' }}</button>
            </template>
            <template v-else-if="lm.paso === 'revisar'">
              <button type="button" class="btn ghost" @click="volverAElegir">Volver</button>
              <HoldButton :disabled="lm.revisando || !nRevisadas" @confirm="confirmar(true)">Cerrar sin guardar</HoldButton>
              <HoldButton :disabled="lm.revisando || !nRevisadas" @confirm="confirmar()">Cerrar {{ nRevisadas || '' }}</HoldButton>
            </template>
            <template v-else-if="lm.paso === 'cerrando'">
              <span class="nota">No cierres esta ventana</span>
            </template>
            <template v-else>
              <button v-if="fallidas.length" type="button" class="btn ghost" @click="reintentar(fallidas.map(itemKey))">Reintentar</button>
              <button type="button" class="btn primary" @click="cerrarHoja">Listo</button>
            </template>
          </footer>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.ls {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: flex-end;
  justify-content: center;
}
.ls.side {
  align-items: stretch;
  justify-content: flex-end;
}
.ls-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(100%, 560px);
  height: min(92dvh, 860px);
  min-height: 0;
  background: var(--surface);
  border: 1px solid var(--line-2);
  border-bottom: 0;
  border-radius: 20px 20px 0 0;
  box-shadow: var(--shadow-pop);
  outline: none;
}
.side .ls-panel {
  width: 520px;
  height: 100%;
  border-radius: 0;
  border: 0;
  border-left: 1px solid var(--line-2);
}
.ls-head {
  padding: 10px 18px 8px;
  display: grid;
  gap: 10px;
}
.grip {
  display: block;
  width: 38px;
  height: 4px;
  border-radius: 4px;
  margin: 0 auto;
  background: var(--line-2);
}
.side .grip {
  display: none;
}
.ls-top {
  display: flex;
  align-items: center;
  gap: 10px;
}
.title {
  margin: 0;
  flex: 1;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.mark,
.back,
.x {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  border-radius: var(--r-md);
  border: 0;
  background: var(--bg-2);
  color: var(--text-2);
}
.back,
.x {
  cursor: pointer;
}
.dias {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}
.dias-lbl {
  font-size: 13px;
  color: var(--text-3);
}
.stepper {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--line-2);
  border-radius: 12px;
  background: var(--bg-2);
  overflow: hidden;
}
.stepper button {
  width: 44px;
  height: 40px;
  border: 0;
  background: transparent;
  color: var(--text);
  font-size: 18px;
  cursor: pointer;
}
.stepper button:disabled {
  opacity: 0.35;
  cursor: default;
}
.stepper output {
  min-width: 78px;
  text-align: center;
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.calc {
  opacity: 0.55;
  --sk-bg: linear-gradient(100deg, transparent 30%, color-mix(in srgb, var(--accent) 14%, transparent) 50%, transparent 70%);
  --sk-dur: 1.1s;
}
:root[data-motion='soft'] .calc::after {
  animation: none;
}
.ls-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: 6px 18px 14px;
  display: grid;
  gap: 10px;
  align-content: start;
}
.ls-foot {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  align-items: center;
  gap: 10px;
  padding: 12px 18px calc(12px + env(safe-area-inset-bottom));
  border-top: 1px solid var(--line);
  background: var(--surface);
}
.grupo {
  display: grid;
  gap: 6px;
}
.g-name {
  margin: 8px 0 0;
  font-size: var(--t-sm);
  font-weight: 600;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.fila,
.res {
  display: flex;
  gap: 4px;
  align-items: flex-start;
  min-width: 0;
  padding: 6px 10px 8px 2px;
  border-radius: 12px;
  background: var(--bg-2);
  border: 1px solid var(--line);
  transition: border-color 0.2s, background 0.2s;
}
.fila.on {
  border-color: color-mix(in srgb, var(--accent) 55%, transparent);
}
.fila.off {
  opacity: 0.6;
  padding-left: 12px;
}
.check {
  flex: none;
  display: grid;
  place-items: center;
  width: 44px;
  height: 44px;
  border: 0;
  background: transparent;
  cursor: pointer;
}
.box {
  display: grid;
  place-items: center;
  width: 22px;
  height: 22px;
  border-radius: 7px;
  border: 1.5px solid var(--line-2);
  color: transparent;
  transition: background 0.2s, color 0.2s, border-color 0.2s, transform 0.3s var(--spring);
}
.check[aria-checked='true'] .box {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--bg);
  transform: scale(1.06);
}
.f-main {
  flex: 1;
  min-width: 0;
  padding-top: 8px;
  display: grid;
  gap: 3px;
}
.f-line {
  display: flex;
  align-items: center;
  gap: 8px;
}
.f-label {
  flex: 1;
  min-width: 0;
  font-size: 14px;
  overflow-wrap: anywhere;
}
.ver {
  border: 0;
  background: transparent;
  color: var(--accent);
  font-size: var(--t-md);
  padding: 6px 4px;
  cursor: pointer;
}
.f-ses,
.f-pend,
.f-why {
  margin: 0;
  font-size: var(--t-md);
  line-height: 1.4;
  color: var(--text-3);
  overflow-wrap: anywhere;
}
.f-pend {
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.f-why {
  display: flex;
  gap: 5px;
  align-items: center;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 2px;
}
.chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  border-radius: var(--r-pill);
  font-size: var(--t-sm);
  background: var(--surface);
  border: 1px solid var(--line-2);
  color: var(--text-2);
  max-width: 100%;
  overflow-wrap: anywhere;
}
.chip[data-r='mergeada'] {
  color: var(--accent);
}
.ver-box {
  margin-top: 4px;
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: var(--surface);
  border: 1px solid var(--line);
  font-size: var(--t-md);
  display: grid;
  gap: 4px;
}
.ver-box p {
  margin: 0;
  overflow-wrap: anywhere;
}
.ver-hint {
  color: var(--text-3);
}
.nota {
  margin: 4px 0 0;
  font-size: var(--t-md);
  line-height: 1.5;
  color: var(--text-3);
}
.nota code {
  font-family: var(--font-mono);
}
.vacio {
  margin: 24px 0;
  text-align: center;
  color: var(--text-3);
  font-size: 14px;
}
.aviso,
.motivo {
  display: flex;
  gap: 7px;
  align-items: flex-start;
  margin: 0;
  padding: 9px 11px;
  border-radius: var(--r-md);
  font-size: 13px;
  background: var(--danger-soft);
  color: var(--danger-ink);
}
.rev {
  display: grid;
  gap: 6px;
}
.rev.amber .motivo {
  background: var(--st-blocked-soft);
  color: var(--text);
}
.res {
  align-items: center;
  padding: 6px 12px;
  margin-bottom: 6px;
  overflow: hidden;
}
.res .f-main {
  padding-top: 0;
}
.res-ico {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  margin-right: 8px;
}
.res.ok .res-ico {
  background: var(--accent);
  color: var(--bg);
}
.res.ko {
  border-color: color-mix(in srgb, var(--danger) 55%, transparent);
}
.res.ko .res-ico {
  background: var(--danger-soft);
  color: var(--danger-ink);
}
.resumen {
  margin: 8px 0 0;
  font-family: var(--font-display);
  font-size: 18px;
  font-weight: 600;
  text-align: center;
}
.skel {
  display: grid;
  gap: 8px;
}
.skel i {
  display: block;
  height: 64px;
  border-radius: 12px;
  background: var(--bg-2);
  --sk-bg: linear-gradient(100deg, transparent 30%, color-mix(in srgb, var(--accent) 12%, transparent) 50%, transparent 70%);
  --sk-dur: 1.1s;
}
:root[data-motion='soft'] .skel i::after {
  animation: none;
}
.btn {
  min-height: 44px;
  padding: 0 18px;
  border-radius: 12px;
  border: 1px solid var(--line-2);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  background: var(--bg-2);
  color: var(--text);
}
.btn.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--bg);
}
.btn.ghost {
  background: transparent;
}
.btn:disabled {
  opacity: 0.4;
  cursor: default;
}
@media (max-width: 639px) {
  .ls-panel {
    width: 100%;
  }
}
</style>

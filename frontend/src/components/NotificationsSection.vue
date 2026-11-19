<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { disablePush, enablePush, probarEnvio, pushState, refreshPush, runProbarAviso, setPushPref, testCierre, testPush } from '../state/push'
import { piezas } from '../piezas'
import { gsap, isSoft, ring, useGsap } from '../motion'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'

const { run } = useGsap()
const root = ref<HTMLElement | null>(null)
const bell = ref<HTMLElement | null>(null)
const tested = ref(false)
let testedTimer: ReturnType<typeof setTimeout> | undefined
const probado = ref<Record<string, boolean>>({})
const probadoTimers: Record<string, ReturnType<typeof setTimeout>> = {}

const notifPiezas = piezas().flatMap((p) => (p.notificaciones ? [p.notificaciones] : []))

type KindPruebaAviso = string

type FilaPrueba = { kind: KindPruebaAviso; label: string }

const filasPrueba = computed((): FilaPrueba[] => {
  const base: FilaPrueba[] = [
    { kind: 'asks', label: 'Te pregunta' },
    { kind: 'blocked', label: 'Necesita permiso' },
    { kind: 'done', label: 'Terminó' },
    { kind: 'terminal', label: 'Terminal' },
    ...notifPiezas.map((n) => n.filaPrueba),
    { kind: 'cierre', label: 'Cierre del día' },
    { kind: 'encadenar', label: 'Encadenar' },
    { kind: 'vigia', label: 'Vigía' },
    { kind: 'mr', label: 'MR' },
    { kind: 'entorno', label: 'Entornos' },
  ]
  return base
})

const enviandoPrueba = ref<Record<string, boolean>>({})
type FeedbackLinea = { notch?: string; celu?: string }
const feedbackPrueba = ref<Record<string, FeedbackLinea>>({})

function claveEnvio(kind: string, dest: 'notch' | 'celu'): string {
  return `${kind}:${dest}`
}

async function enviarPrueba(kind: KindPruebaAviso, dest: 'notch' | 'celu') {
  const ck = claveEnvio(kind, dest)
  if (enviandoPrueba.value[ck]) return
  enviandoPrueba.value = { ...enviandoPrueba.value, [ck]: true }
  const prev = feedbackPrueba.value[kind] ?? {}
  feedbackPrueba.value = { ...feedbackPrueba.value, [kind]: { ...prev, [dest]: '' } }
  try {
    const r = await runProbarAviso(kind, dest)
    const msg = r.ok ? 'Enviado' : r.message
    const cur = feedbackPrueba.value[kind] ?? {}
    feedbackPrueba.value = { ...feedbackPrueba.value, [kind]: { ...cur, [dest]: msg } }
  } finally {
    enviandoPrueba.value = { ...enviandoPrueba.value, [ck]: false }
  }
}

function muestraNotch(kind: KindPruebaAviso): boolean {
  return pushState.status === 'programa' && (kind === 'asks' || kind === 'blocked' || kind === 'done')
}

const rows = computed(() => {
  const all: { key: string; label: string; hint: string; probar?: () => Promise<boolean>; probarEtiqueta?: string }[] = [
    { key: 'asks', label: 'Te pregunta', hint: 'Una sesión espera tu respuesta' },
    { key: 'blocked', label: 'Espera aprobación', hint: 'Está frenada en la terminal' },
    { key: 'done', label: 'Terminó', hint: 'Después de trabajar un rato' },
    ...notifPiezas.map((n) => ({ ...n.pref, probar: () => probarEnvio(n.probar), probarEtiqueta: n.probarEtiqueta })),
    { key: 'cierre', label: 'Cierre del día', hint: 'Lun a vie a las 17:30 con lo que terminó, lo que te espera y ramas sin integrar', probar: testCierre, probarEtiqueta: 'Probar el cierre del día' },
    { key: 'mrs', label: 'Merge requests', hint: 'Falla un pipeline, te aprueban, te comentan o te piden revisión' },
    { key: 'entornos', label: 'Entornos', hint: 'Si un contenedor se cae solo o queda con problemas' },
    { key: 'pestana', label: 'Pedidos de pestaña', hint: 'Cuando una sesión quiere abrir una pestaña nueva en otra carpeta' },
  ]
  return all
})

function wiggle() {
  if (!bell.value || isSoft()) return
  const el = bell.value
  run(() => gsap.fromTo(el, { rotation: 0 }, { keyframes: [{ rotation: -22 }, { rotation: 18 }, { rotation: -11 }, { rotation: 6 }, { rotation: 0 }], duration: 0.9, ease: 'power2.inOut', transformOrigin: '50% 12%' }))
  ring(el, getComputedStyle(el).color, 40)
}

async function enable() {
  if (await enablePush()) wiggle()
}

async function test() {
  if (!(await testPush())) return
  tested.value = true
  clearTimeout(testedTimer)
  testedTimer = setTimeout(() => (tested.value = false), 2200)
}

async function probarFila(key: string, probar: () => Promise<boolean>) {
  if (!(await probar())) return
  probado.value = { ...probado.value, [key]: true }
  clearTimeout(probadoTimers[key])
  probadoTimers[key] = setTimeout(() => (probado.value = { ...probado.value, [key]: false }), 2200)
}

watch(
  () => pushState.status,
  async (_s, old) => {
    if (old === undefined || isSoft()) return
    await nextTick()
    const kids = root.value?.querySelectorAll('.n-body > *')
    if (kids?.length) run(() => gsap.from(kids, { y: 6, opacity: 0, duration: 0.4, ease: 'power3.out', stagger: 0.045, clearProps: 'transform,opacity' }))
  },
)

onMounted(() => void refreshPush())
</script>

<template>
  <section ref="root" class="notif" aria-label="Notificaciones">
    <header class="n-head">
      <span ref="bell" class="n-bell" :data-on="pushState.status === 'on'" aria-hidden="true">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round">
          <path d="M6 16.5V11a6 6 0 0 1 12 0v5.5l1.5 2h-15L6 16.5Z" />
          <path d="M10 21h4" />
          <path v-if="pushState.status !== 'on'" class="n-slash" d="M4 4l16 16" />
        </svg>
      </span>
      <span class="n-title">Notificaciones</span>
      <span v-if="pushState.status === 'on'" class="n-chip">Activadas</span>
    </header>

    <Transition name="nswap" mode="out-in">
      <div :key="pushState.status" class="n-body">
        <p v-if="pushState.status === 'checking'" class="n-skel" aria-hidden="true" />

        <p v-else-if="pushState.status === 'unsupported'" class="n-note">
          Este navegador no puede recibir avisos. Hace falta abrir Colmena por HTTPS desde un navegador compatible.
        </p>

        <div v-else-if="pushState.status === 'install'" class="n-card">
          <span class="n-card-ico" aria-hidden="true">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M12 15V4M8 8l4-4 4 4" /><path d="M6 11H5v9h14v-9h-1" /></svg>
          </span>
          <p>Agregala a la pantalla de inicio para recibir avisos.<small>Compartir, después «Agregar a inicio». Abrila desde ahí y volvé a este menú.</small></p>
        </div>

        <p v-else-if="pushState.status === 'denied'" class="n-note">
          Bloqueaste los avisos para este sitio. Habilitalos desde los ajustes del navegador (en iPhone, Ajustes, Notificaciones, Colmena) y volvé a abrir este menú.
        </p>

        <p v-else-if="pushState.status === 'programa'" class="n-note">
          En el programa de Windows los avisos salen del notch.
        </p>

        <template v-else-if="pushState.status === 'off'">
          <button class="n-cta" :disabled="pushState.busy" @click="enable">
            <span v-if="pushState.busy" class="n-spin" aria-hidden="true" />
            {{ pushState.busy ? 'Activando…' : 'Activar en este dispositivo' }}
          </button>
          <p class="n-hint">Te avisa cuando una sesión pregunta, se frena o termina. Dispositivo: {{ pushState.device }}.</p>
        </template>

        <template v-else>
          <div class="n-rows" role="group" aria-label="Qué avisar">
            <template v-for="r in rows" :key="r.key">
              <div v-if="r.probar" class="n-split">
                <button class="n-row" role="switch" :aria-checked="pushState.prefs[r.key]" @click="setPushPref(r.key, !pushState.prefs[r.key])">
                  <span class="n-row-txt">{{ r.label }}<small>{{ r.hint }}</small></span>
                  <i class="n-sw" aria-hidden="true" />
                </button>
                <button
                  class="n-mini"
                  :disabled="pushState.busy"
                  :data-done="!!probado[r.key]"
                  :aria-label="r.probarEtiqueta"
                  @click="probarFila(r.key, r.probar)"
                >
                  <Transition name="nlbl" mode="out-in">
                    <span v-if="probado[r.key]" key="ok" class="n-lbl"><Icon name="check" :size="12" /> Enviado</span>
                    <span v-else key="t" class="n-lbl">Probar</span>
                  </Transition>
                </button>
              </div>
              <button v-else class="n-row" role="switch" :aria-checked="pushState.prefs[r.key]" @click="setPushPref(r.key, !pushState.prefs[r.key])">
                <span class="n-row-txt">{{ r.label }}<small>{{ r.hint }}</small></span>
                <i class="n-sw" aria-hidden="true" />
              </button>
            </template>
            <button class="n-row n-row-text" role="switch" :aria-checked="pushState.prefs.texto" @click="setPushPref('texto', !pushState.prefs.texto)">
              <span class="n-row-txt">Mostrar texto<small>El pendiente de la sesión en el aviso</small></span>
              <i class="n-sw" aria-hidden="true" />
            </button>
          </div>
          <div class="n-actions">
            <button class="n-btn" :disabled="pushState.busy" :data-done="tested" @click="test">
              <Transition name="nlbl" mode="out-in">
                <span v-if="tested" key="ok" class="n-lbl"><Icon name="check" :size="13" /> Enviado</span>
                <span v-else key="t" class="n-lbl">Probar</span>
              </Transition>
            </button>
            <button class="n-btn quiet" :disabled="pushState.busy" @click="disablePush">Desactivar</button>
          </div>
        </template>

        <InlineAlert v-if="pushState.error" :detalle="pushState.errorDetalle">{{ pushState.error }}</InlineAlert>

        <div class="n-probar-wrap" role="region" aria-label="Probar avisos">
          <p class="n-probar-title">Probar avisos</p>
          <div class="n-probar-list">
            <div v-for="f in filasPrueba" :key="f.kind" class="n-probar-row" :data-kind="f.kind">
              <span class="n-probar-label">{{ f.label }}</span>
              <div class="n-probar-actions">
                <button
                  v-if="muestraNotch(f.kind)"
                  type="button"
                  class="n-probar-btn"
                  :disabled="enviandoPrueba[claveEnvio(f.kind, 'notch')]"
                  :aria-busy="enviandoPrueba[claveEnvio(f.kind, 'notch')]"
                  @click="enviarPrueba(f.kind, 'notch')"
                >
                  En el notch
                </button>
                <button
                  type="button"
                  class="n-probar-btn"
                  :disabled="enviandoPrueba[claveEnvio(f.kind, 'celu')]"
                  :aria-busy="enviandoPrueba[claveEnvio(f.kind, 'celu')]"
                  @click="enviarPrueba(f.kind, 'celu')"
                >
                  Al celu
                </button>
              </div>
              <p
                v-if="feedbackPrueba[f.kind]?.notch || feedbackPrueba[f.kind]?.celu"
                class="n-probar-fb"
                role="status"
              >
                <template v-if="feedbackPrueba[f.kind]?.notch">
                  <span>Notch: {{ feedbackPrueba[f.kind]!.notch }}</span>
                </template>
                <template v-if="feedbackPrueba[f.kind]?.celu">
                  <span v-if="feedbackPrueba[f.kind]?.notch"> · </span>
                  <span>Celu: {{ feedbackPrueba[f.kind]!.celu }}</span>
                </template>
              </p>
            </div>
          </div>
        </div>
      </div>
    </Transition>
  </section>
</template>

<style scoped>
.notif {
  padding: 8px 4px 6px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--line);
}
.n-head {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 0 6px 8px 6px;
  font-size: 13px;
  color: var(--text-2);
}
.n-bell {
  display: grid;
  place-items: center;
  width: 15px;
  height: 15px;
  color: var(--text-3);
  transition: color 0.4s;
}
.n-bell[data-on='true'] { color: var(--accent); }
.n-slash { stroke-width: 1.7; opacity: 0.8; }
.n-title { flex: 1; }
.n-chip {
  height: 20px;
  padding: 0 8px;
  display: inline-flex;
  align-items: center;
  border-radius: var(--r-pill);
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.n-body { display: grid; gap: 8px; padding: 0 6px; }
.n-note, .n-hint, .n-err {
  margin: 0;
  font-size: 12px;
  line-height: 1.45;
  color: var(--text-3);
}
.n-hint { color: var(--text-4); }
.n-err { color: var(--danger); }
.n-skel {
  height: 34px;
  margin: 0;
  border-radius: var(--r-md);
  background: linear-gradient(100deg, var(--bg-2) 30%, var(--surface-hover) 50%, var(--bg-2) 70%) 0 0 / 220% 100%;
  animation: shimmer 1.4s linear infinite;
}
@keyframes shimmer { to { background-position: -120% 0; } }

.n-card {
  display: flex;
  gap: 10px;
  padding: 10px;
  border-radius: var(--r-md);
  background: var(--accent-soft);
  box-shadow: inset 0 0 0 1px var(--accent-line);
}
.n-card p { margin: 0; font-size: var(--t-md); line-height: 1.4; color: var(--text); }
.n-card small { display: block; margin-top: 3px; font-size: var(--t-sm); color: var(--text-3); }
.n-card-ico { color: var(--accent); flex: none; margin-top: 1px; }

.n-cta {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 36px;
  border-radius: var(--r-md);
  font-size: 13px;
  font-weight: 600;
  color: var(--accent-ink);
  background: var(--accent);
  transition: scale 0.3s var(--spring), opacity 0.2s, filter 0.2s;
}
.n-cta:hover { filter: brightness(1.08); }
.n-cta:active { scale: var(--press-scale); }
.n-cta:disabled { opacity: 0.7; pointer-events: none; }
.n-spin {
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--accent-ink) 30%, transparent);
  border-top-color: var(--accent-ink);
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { rotate: 360deg; } }

.n-rows { display: grid; gap: 1px; }
.n-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin: 0 -6px;
  padding: 7px 6px;
  width: calc(100% + 12px);
  border-radius: 8px;
  text-align: left;
  font-size: 13px;
  color: var(--text-2);
  transition: background 0.2s, color 0.2s;
}
.n-row:hover { background: var(--surface-hover); color: var(--text); }
.n-row-text { margin-top: 4px; border-top: 1px solid var(--line); border-radius: 0 0 8px 8px; padding-top: 10px; }
.n-row-txt { display: grid; gap: 1px; }
.n-row-txt small { font-size: 11px; color: var(--text-4); }
.n-sw {
  position: relative;
  flex: none;
  width: 34px;
  height: 20px;
  border-radius: var(--r-pill);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.3s, box-shadow 0.3s;
}
.n-sw::after {
  content: '';
  position: absolute;
  top: 3px;
  left: 3px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--text-3);
  transition: translate 0.45s var(--spring), background 0.3s;
}
.n-row[aria-checked='true'] .n-sw { background: var(--accent); box-shadow: none; }
.n-row[aria-checked='true'] .n-sw::after { translate: 14px 0; background: var(--accent-ink); }
.n-row:active .n-sw::after { scale: 1.15 1; }

.n-split { display: flex; align-items: center; gap: 6px; margin: 0 -6px; }
.n-split .n-row { flex: 1; min-width: 0; margin: 0; width: auto; }
.n-mini {
  flex: none;
  height: 26px;
  min-width: 56px;
  padding: 0 9px;
  border-radius: 7px;
  font-size: var(--t-sm);
  font-weight: 560;
  color: var(--text-2);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), opacity 0.2s, box-shadow 0.3s;
}
.n-mini:hover { background: var(--surface-hover); color: var(--text); }
.n-mini:active { scale: var(--press-scale); }
.n-mini:disabled { opacity: 0.5; pointer-events: none; }
.n-mini[data-done='true'] { color: var(--st-done); background: var(--st-done-soft); box-shadow: none; }

.n-actions { display: flex; gap: 6px; margin-top: 2px; }
.n-btn {
  flex: 1;
  height: 30px;
  border-radius: 8px;
  font-size: var(--t-md);
  font-weight: 560;
  color: var(--text);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), opacity 0.2s, box-shadow 0.3s;
}
.n-btn:hover { background: var(--surface-hover); }
.n-btn:active { scale: var(--press-scale); }
.n-btn:disabled { opacity: 0.5; pointer-events: none; }
.n-btn[data-done='true'] { color: var(--st-done); background: var(--st-done-soft); box-shadow: none; }
.n-btn.quiet { color: var(--text-3); background: transparent; box-shadow: none; }
.n-btn.quiet:hover { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, transparent); }
.n-lbl { display: inline-flex; align-items: center; gap: 5px; }

.nswap-enter-active { transition: opacity 0.2s; }
.nswap-leave-active { transition: opacity 0.1s; }
.nswap-enter-from, .nswap-leave-to { opacity: 0; }
.nlbl-enter-active { transition: opacity 0.2s, transform 0.4s var(--spring); }
.nlbl-leave-active { transition: opacity 0.1s; }
.nlbl-enter-from { opacity: 0; transform: translateY(5px); }
.nlbl-leave-to { opacity: 0; }

.n-probar-wrap {
  margin-top: 6px;
  padding-top: 10px;
  border-top: 1px solid var(--line);
}
.n-probar-title {
  margin: 0 0 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-2);
}
.n-probar-list {
  display: grid;
  gap: 8px;
}
.n-probar-row {
  display: grid;
  gap: 4px;
}
.n-probar-label {
  font-size: var(--t-md);
  color: var(--text-2);
}
.n-probar-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.n-probar-btn {
  flex: none;
  min-height: 26px;
  padding: 0 10px;
  border-radius: 7px;
  font-size: var(--t-sm);
  font-weight: 560;
  color: var(--text-2);
  background: var(--bg-2);
  box-shadow: inset 0 0 0 1px var(--line-2);
  transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), opacity 0.2s;
}
.n-probar-btn:hover:not(:disabled) {
  background: var(--surface-hover);
  color: var(--text);
}
.n-probar-btn:active:not(:disabled) {
  scale: var(--press-scale);
}
.n-probar-btn:disabled {
  opacity: 0.5;
  pointer-events: none;
}
.n-probar-fb {
  margin: 0;
  font-size: 11px;
  color: var(--text-3);
  line-height: 1.35;
}
:root[data-motion='soft'] .n-skel {
  animation: none;
}
</style>

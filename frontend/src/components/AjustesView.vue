<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { revokeAllSessions, revokeSessionsErr } from '../state/app'
import { closeAjustes } from '../state/ajustes'
import { abrirLimpieza } from '../state/limpieza'
import { desktop } from '../lib/viewport'
import { useFocusTrap } from '../lib/focusTrap'
import { useKeyboard } from '../lib/keyboard'
import { setTheme, theme } from '../lib/theme'
import { motionPref, setMotion, systemReduced } from '../motion'
import type { Theme } from '../lib/storage'
import { gruposDeAtajos } from '../lib/atajos'
import Icon from './Icon.vue'
import SegControl from './SegControl.vue'
import ClaudePanel from './ClaudePanel.vue'
import NotificationsSection from './NotificationsSection.vue'
import MemoriaSection from './MemoriaSection.vue'
import PermisosHistorial from './PermisosHistorial.vue'
import ViewFrame from './ViewFrame.vue'

type IconName = InstanceType<typeof Icon>['$props']['name']
const keyboard = useKeyboard()
const frame = ref<{ $el: HTMLElement } | null>(null)
const panel = ref<HTMLElement | null>(null)
const root = computed(() => frame.value?.$el ?? null)
const { onKeydown } = useFocusTrap(panel, () => true, { onEscape: closeAjustes })
const tablist = ref<HTMLElement | null>(null)
const PESTANA_KEY = 'colmena.ajustes.pestana'
const active = ref('')

const sections = computed<{ id: string; title: string; desc: string; icon: IconName }[]>(() => [
  { id: 'apariencia', title: 'Apariencia', desc: 'Cómo se ve y cómo se mueve.', icon: 'sun' },
  { id: 'claude', title: 'Claude', desc: 'Cuánto usaron tus sesiones y cuánto te queda del plan.', icon: 'sparkle' },
  { id: 'memoria', title: 'Memoria', desc: 'Lo que se guarda de tus sesiones pasadas.', icon: 'brain' },
  { id: 'permisos', title: 'Permisos', desc: 'Lo que se decidió sobre los permisos que pidieron tus sesiones.', icon: 'lock' },
  { id: 'avisos', title: 'Avisos', desc: 'Qué te llega al celu y cuándo.', icon: 'pulse' },
  { id: 'atajos', title: 'Atajos', desc: 'Las teclas que te ahorran clics.', icon: 'keyboard' },
  ...(desktop.value ? [{ id: 'mantenimiento', title: 'Mantenimiento', desc: 'Ordená las sesiones que quedaron quietas.', icon: 'broom' as IconName }] : []),
  { id: 'sesion', title: 'Sesión', desc: 'Salir en todos tus dispositivos.', icon: 'power' },
])

const THEMES = [
  { value: 'light' as Theme, label: 'Claro' },
  { value: 'dark' as Theme, label: 'Oscuro' },
]
const MOTIONS = [
  { value: 'full' as const, label: 'Completas' },
  { value: 'soft' as const, label: 'Suaves' },
]
const motionValue = computed(() => (systemReduced.value ? 'soft' : motionPref.value))
let themeSeg: HTMLElement | null = null
const setSeg = (c: unknown) => (themeSeg = (c as { $el?: HTMLElement } | null)?.$el ?? null)
function pickTheme(t: Theme) {
  setTheme(t, themeSeg)
}

const confirming = ref(false)
const revoking = ref(false)
async function revoke() {
  revoking.value = true
  revokeSessionsErr.value = ''
  if (!(await revokeAllSessions())) revoking.value = false
}
function limpiar() {
  closeAjustes()
  setTimeout(abrirLimpieza, 60)
}

const esMac = typeof navigator !== 'undefined' && /mac/i.test(navigator.platform || navigator.userAgent || '')
const grupos = gruposDeAtajos()
const teclasDe = (teclas: string[], mod?: boolean) => (esMac && mod ? teclas.map((t) => (t === 'Ctrl' ? '⌘' : t)) : teclas)
function partes(teclas: string[], mod?: boolean): { txt: string; tecla: boolean }[] {
  const out: { txt: string; tecla: boolean }[] = []
  teclasDe(teclas, mod).forEach((t, i, arr) => {
    if (t === '–') return void out.push({ txt: 'a', tecla: false })
    if (i && arr[i - 1] !== '–') out.push({ txt: '+', tecla: false })
    out.push({ txt: t, tecla: true })
  })
  return out
}

const current = computed(() => sections.value.find((x) => x.id === active.value) ?? sections.value[0])

function recordada(): string {
  try {
    return localStorage.getItem(PESTANA_KEY) ?? ''
  } catch {
    return ''
  }
}
function recordar(id: string) {
  try {
    localStorage.setItem(PESTANA_KEY, id)
  } catch {
    /* sin almacenamiento: la pestaña no se recuerda */
  }
}
active.value = sections.value.find((x) => x.id === recordada())?.id ?? sections.value[0].id

function goTo(id: string, focus = false) {
  active.value = id
  recordar(id)
  if (focus) nextTick(() => tablist.value?.querySelector<HTMLElement>(`#aj-tab-${id}`)?.focus())
}

function onTabsKey(e: KeyboardEvent) {
  const ids = sections.value.map((x) => x.id)
  const i = ids.indexOf(current.value.id)
  let n = -1
  if (e.key === 'ArrowDown' || e.key === 'ArrowRight') n = (i + 1) % ids.length
  else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') n = (i - 1 + ids.length) % ids.length
  else if (e.key === 'Home') n = 0
  else if (e.key === 'End') n = ids.length - 1
  if (n < 0) return
  e.preventDefault()
  goTo(ids[n], true)
}

function centrarActiva() {
  tablist.value?.querySelector<HTMLElement>(`#aj-tab-${current.value.id}`)?.scrollIntoView?.({ inline: 'center', block: 'nearest' })
}
watch(() => current.value.id, () => nextTick(centrarActiva))

onMounted(async () => {
  panel.value = root.value
  await nextTick()
  centrarActiva()
})
</script>

<template>
  <ViewFrame
    ref="frame"
    class="aj"
    :class="{ desk: desktop }"
    role="dialog"
    aria-modal="true"
    aria-label="Ajustes"
    tabindex="-1"
    title="Ajustes"
    sticky-head
    show-back
    :back-icon="desktop ? 'close' : 'back'"
    :back-label="desktop ? 'Cerrar Ajustes' : 'Volver'"
    :style="keyboard.open.value && keyboard.height.value ? { height: `${keyboard.height.value}px`, top: `${keyboard.top.value}px`, bottom: 'auto' } : undefined"
    @back="closeAjustes"
    @keydown="onKeydown"
  >
    <template #back>
      <button type="button" class="btn btn-back btn-icon" :class="{ 'btn-back--wide': desktop }" :aria-label="desktop ? 'Cerrar Ajustes' : 'Volver'" @click="closeAjustes">
        <Icon :name="desktop ? 'close' : 'back'" :size="18" />
        <span v-if="desktop" class="esc mono">Esc</span>
      </button>
    </template>

    <div class="body">
      <div
        ref="tablist"
        role="tablist"
        class="tabs"
        :class="{ nav: desktop }"
        :aria-orientation="desktop ? 'vertical' : 'horizontal'"
        aria-label="Secciones de Ajustes"
        @keydown="onTabsKey"
      >
        <button
          v-for="s in sections"
          :id="`aj-tab-${s.id}`"
          :key="s.id"
          type="button"
          role="tab"
          class="tab"
          :class="{ on: current.id === s.id }"
          :aria-selected="current.id === s.id"
          aria-controls="aj-panel"
          :tabindex="current.id === s.id ? 0 : -1"
          @click="goTo(s.id)"
        >
          <Icon :name="s.icon" :size="16" />
          <span>{{ s.title }}</span>
        </button>
      </div>

      <div class="scroll">
        <div id="aj-panel" class="col" role="tabpanel" :aria-labelledby="`aj-tab-${current.id}`">
          <Transition name="pane" mode="out-in">
          <section :key="current.id" class="sec" :aria-labelledby="`aj-${current.id}`">
            <header class="s-head">
              <span class="s-ico" aria-hidden="true"><Icon :name="current.icon" :size="16" /></span>
              <div>
                <h2 :id="`aj-${current.id}`">{{ current.title }}</h2>
                <p>{{ current.desc }}</p>
              </div>
            </header>

            <div v-if="current.id === 'apariencia'" class="ui-card rows">
              <div class="row">
                <span class="r-txt">Tema<small>Claro u oscuro, el cambio se nota en toda la app.</small></span>
                <SegControl :ref="setSeg" :model-value="theme" :options="THEMES" label="Tema" class="r-seg" @update:model-value="pickTheme" />
              </div>
              <div class="row">
                <span class="r-txt">Animaciones<small>{{ systemReduced ? 'El sistema pide movimiento reducido.' : 'Suaves deja solo transiciones cortas.' }}</small></span>
                <SegControl :model-value="motionValue" :options="MOTIONS" label="Animaciones" :disabled="systemReduced" class="r-seg" @update:model-value="setMotion" />
              </div>
            </div>

            <ClaudePanel v-else-if="current.id === 'claude'" />

            <MemoriaSection v-else-if="current.id === 'memoria'" />

            <PermisosHistorial v-else-if="current.id === 'permisos'" />

            <div v-else-if="current.id === 'avisos'" class="ui-card notif"><NotificationsSection /></div>


            <div v-else-if="current.id === 'atajos'" class="atajos">
              <p v-if="!desktop" class="at-nota">Los atajos son para teclado; en el celu sirven si conectás uno.</p>
              <div v-for="g in grupos" :key="g.grupo" class="ui-card at-grupo">
                <h3>{{ g.grupo }}</h3>
                <ul>
                  <li v-for="(a, i) in g.items" :key="i" class="atajo">
                    <span class="at-keys">
                      <template v-for="(p, k) in partes(a.teclas, a.mod)" :key="k">
                        <kbd v-if="p.tecla">{{ p.txt }}</kbd>
                        <span v-else class="at-plus" aria-hidden="true">{{ p.txt }}</span>
                      </template>
                      <template v-if="a.tambien">
                        <span class="at-o">o</span>
                        <kbd v-for="(t, k) in teclasDe(a.tambien, a.mod)" :key="k">{{ t }}</kbd>
                      </template>
                    </span>
                    <span class="at-txt">{{ a.que }}<small>{{ a.donde }}</small></span>
                  </li>
                </ul>
              </div>
            </div>

            <div v-else-if="current.id === 'mantenimiento'" class="ui-card rows">
              <button class="row act" @click="limpiar">
                <span class="r-txt">Limpiar sesiones<small>Cierra las que están quietas, con una revisión antes.</small></span>
                <Icon name="chevron" :size="16" />
              </button>
            </div>

            <div v-else class="ui-card rows">
              <div v-if="!confirming" class="row">
                <span class="r-txt">Salir de Colmena<small>En todos tus dispositivos.</small></span>
                <button type="button" class="btn btn-danger-soft" @click="confirming = true">Salir</button>
              </div>
              <div v-else class="confirm">
                <p>Salís de Colmena en todos tus dispositivos, este incluido, y vas a tener que poner el PIN de nuevo. Las terminales y las sesiones de Claude no se tocan.</p>
                <p v-if="revokeSessionsErr" class="revoke-err" role="alert">{{ revokeSessionsErr }}</p>
                <div class="c-actions">
                  <button type="button" class="btn btn-ghost" :disabled="revoking" @click="confirming = false">Cancelar</button>
                  <button type="button" class="btn btn-danger" :disabled="revoking" @click="revoke">{{ revoking ? 'Saliendo…' : 'Salir' }}</button>
                </div>
              </div>
            </div>
          </section>
          </Transition>
        </div>
      </div>
    </div>
  </ViewFrame>
</template>

<style scoped>
.aj {
  position: fixed;
  inset: 0;
  z-index: 80;
  background-image: radial-gradient(1000px 420px at 0% -10%, var(--accent-soft), transparent 60%);
  outline: none;
  overflow: hidden;
}
.aj :deep(.vf-body) {
  flex: 1;
  min-height: 0;
  padding: 0;
  gap: 0;
  overflow: hidden;
}
.esc {
  height: 20px;
  padding: 0 6px;
  display: inline-grid;
  place-items: center;
  border-radius: 6px;
  font: 600 10.5px/1 var(--font-mono);
  color: var(--text-3);
  background: var(--keycap);
  box-shadow: inset 0 0 0 1px var(--keycap-rim);
}
.body { flex: 1; min-height: 0; display: flex; flex-direction: column; width: 100%; }
.desk .body { flex-direction: row; }
.tabs { flex: none; display: flex; gap: 6px; overflow-x: auto; overscroll-behavior-x: contain; scrollbar-width: none; padding: 8px var(--gutter); border-bottom: 1px solid var(--line); }
.tabs::-webkit-scrollbar { display: none; }
.tabs .tab { flex: none; height: 44px; padding: 0 16px; }
.tabs .tab.on { color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.tabs.nav .tab { height: 40px; padding: 0 14px; }
.tabs.nav .tab.on { color: var(--text); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); }
.scroll {
  flex: 1;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  padding: var(--view-pad-top) var(--gutter) calc(40px + env(safe-area-inset-bottom));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
}
.col { display: grid; gap: 30px; max-width: var(--read-max); margin: 0; min-width: 0; width: 100%; }
.sec { min-width: 0; display: grid; gap: 12px; }
.s-head { display: flex; align-items: center; gap: 12px; padding: 0 2px; }
.s-ico { flex: none; width: 34px; height: 34px; display: grid; place-items: center; border-radius: var(--r-md); color: var(--accent); background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-line); }
.s-head h2 { margin: 0; font-family: var(--font-display); font-size: 18px; font-weight: 620; letter-spacing: -0.015em; }
.s-head p { margin: 1px 0 0; font-size: var(--t-md); color: var(--text-3); }
.rows { padding: 4px 18px; }
.row { display: flex; flex-direction: column; align-items: stretch; gap: 12px; width: 100%; padding: 16px 0; text-align: left; }
.row + .row, .row + .confirm { border-top: 1px solid var(--line); }
.r-txt { display: grid; gap: 3px; font-size: 14px; font-weight: 540; color: var(--text); }
.r-txt small { font-size: 12px; font-weight: 400; line-height: 1.4; color: var(--text-4); }
.act { flex-direction: row; align-items: center; justify-content: space-between; color: var(--text-3); transition: color 0.2s; }
.act:hover { color: var(--text); }
.notif { padding: 6px 14px 10px; }
.notif :deep(.notif) { border-bottom: 0; margin-bottom: 0; padding: 10px 2px 4px; }
.confirm { padding: 16px 0; }
.confirm p { margin: 0 0 14px; font-size: 13px; line-height: 1.5; color: var(--text-2); }
.c-actions { display: flex; gap: 8px; justify-content: flex-end; }

.desk .body { max-width: none; width: 100%; margin: 0; }
.nav.tabs { flex: none; width: 220px; border-bottom: 0; overflow: visible; padding: 28px 12px 28px var(--gutter); display: flex; flex-direction: column; gap: 4px; align-self: flex-start; position: sticky; top: 0; }
.tab { display: flex; align-items: center; gap: 11px; height: 40px; padding: 0 14px; border-radius: 12px; font-size: var(--t-lg); font-weight: 540; color: var(--text-3); text-align: left; transition: background 0.25s, color 0.25s, scale 0.3s var(--spring); }
@media (hover: hover) and (pointer: fine) {
  .tab:hover { color: var(--text); background: var(--surface-hover); }
}
.tab:active { scale: var(--press-scale); }
.tab.on { color: var(--text); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); }
.tab.on :deep(svg) { color: var(--accent); }
.pane-enter-active, .pane-leave-active { transition: opacity 0.18s ease, transform 0.18s ease; }
.pane-enter-from { opacity: 0; transform: translateY(6px); }
.pane-leave-to { opacity: 0; transform: translateY(-6px); }
@media (prefers-reduced-motion: reduce) {
  .pane-enter-active, .pane-leave-active { transition: none; }
}
.desk .scroll { padding: 28px var(--gutter) 80px; }
.desk .col { max-width: 860px; margin: 0; gap: 40px; }
.desk .row { flex-direction: row; align-items: center; justify-content: space-between; gap: 24px; }
.desk .r-seg { width: 260px; flex: none; }
@media (max-width: 1023px) { .r-seg { width: 100%; } }
.atajos { display: grid; gap: 14px; }
.at-nota { margin: 0; font-size: var(--t-md); color: var(--text-3); }
.at-grupo { padding: 14px 18px 6px; }
.at-grupo h3 { margin: 0 0 4px; font-size: 12px; font-weight: 620; letter-spacing: 0.04em; text-transform: uppercase; color: var(--text-4); }
.at-grupo ul { list-style: none; margin: 0; padding: 0; }
.atajo { display: flex; flex-direction: column; gap: 6px; padding: 12px 0; }
.atajo + .atajo { border-top: 1px solid var(--line); }
.at-keys { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; }
.at-plus, .at-o { font-size: 12px; color: var(--text-4); }
kbd { display: inline-grid; place-items: center; min-width: 24px; height: 24px; padding: 0 7px; border-radius: 6px; font: 600 12px/1 var(--font-mono); color: var(--text-2); background: var(--keycap); box-shadow: inset 0 0 0 1px var(--line); }
.at-txt { display: grid; gap: 2px; font-size: 14px; color: var(--text); }
.at-txt small { font-size: 12px; color: var(--text-4); }
.desk .atajo { flex-direction: row; align-items: center; gap: 20px; }
.desk .at-keys { flex: none; width: 240px; }
</style>

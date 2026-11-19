<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { agruparAvisos, horaDeAviso, iconoAviso } from '../lib/avisos'
import { piezas } from '../piezas'
import { desktop } from '../lib/viewport'
import { gsap, haptic, isSoft, useGsap } from '../motion'
import { abrirAvisos, av, cerrarAvisos, irAAviso, marcarTodoLeido, masAvisos, refrescarAvisos } from '../state/avisos'
import {
  abrirPedidoPestana,
  pedidoPestanaPorId,
  pedidoPestanaPendiente,
  pedidosPestana,
  rechazarPedidoPestana,
} from '../state/pedidosPestana'
import ListoOverlay from './ListoOverlay.vue'
import PedidoPestanaCard from './PedidoPestanaCard.vue'
import Icon from './Icon.vue'

const { run } = useGsap()
const btn = ref<HTMLElement | null>(null)
const panel = ref<HTMLElement | null>(null)
const pos = ref({ top: 0, right: 0 })
const grupos = computed(() => agruparAvisos(av.items))
const avisosDePiezas = piezas().flatMap((p) => (p.avisos ? [p.avisos] : []))
const kindsAcento = avisosDePiezas.filter((p) => p.acento).map((p) => p.kind)
const badge = computed(() => (av.noLeidos > 99 ? '99+' : String(av.noLeidos)))

function toggle() {
  haptic(5)
  if (av.open) return cerrarAvisos()
  const r = btn.value?.getBoundingClientRect()
  if (r) pos.value = { top: r.bottom + 10, right: Math.max(8, window.innerWidth - r.right - 4) }
  void abrirAvisos()
}

const { onKeydown } = useFocusTrap(panel, () => av.open, { onEscape: cerrarAvisos })

watch(
  () => av.noLeidos,
  async (n, o) => {
    if (!(n > o) || isSoft() || !btn.value) return
    run(() => gsap.fromTo(btn.value, { rotation: -14 }, { rotation: 0, duration: 0.9, ease: 'elastic.out(1, 0.35)' }))
  },
)

watch(
  () => av.loaded && av.open,
  async (ready) => {
    if (!ready || isSoft()) return
    await nextTick()
    const rows = panel.value?.querySelectorAll('.item')
    if (rows?.length) run(() => gsap.from(Array.from(rows).slice(0, 12), { y: 10, opacity: 0, duration: 0.4, ease: 'power3.out', stagger: 0.03, clearProps: 'transform,opacity' }))
  },
)

function tocar(a: Parameters<typeof irAAviso>[0]) {
  haptic(6)
  irAAviso(a)
}

function cardDeAviso(a: { pedido?: string }) {
  return a.pedido ? pedidoPestanaPorId(a.pedido) : undefined
}
</script>

<template>
  <button ref="btn" class="bell hit" :aria-label="av.noLeidos ? `Avisos, ${av.noLeidos} sin leer` : 'Avisos'" aria-haspopup="dialog" :aria-expanded="av.open" @click="toggle">
    <Icon name="bell" :size="16" />
    <Transition name="pip">
      <b v-if="av.noLeidos" class="pip mono">{{ badge }}</b>
    </Transition>
  </button>

  <Teleport to="body">
    <Transition name="av">
      <div v-if="av.open" class="av" :class="{ wide: desktop }" @keydown="onKeydown">
        <div class="back" @click="cerrarAvisos" />
        <section ref="panel" class="panel" role="dialog" aria-modal="true" aria-label="Avisos" tabindex="-1" :style="desktop ? { top: `${pos.top}px`, right: `${pos.right}px` } : undefined">
          <ListoOverlay :visible="pedidosPestana.listo" :texto="pedidosPestana.listoTxt" />
          <i class="grip" aria-hidden="true" />
          <header class="top">
            <h2><Icon name="bell" :size="17" /> Avisos</h2>
            <button v-if="av.noLeidos" class="mark" @click="marcarTodoLeido"><Icon name="check" :size="13" /> Marcar todo como leído</button>
            <button class="x" aria-label="Cerrar" @click="cerrarAvisos"><Icon name="close" :size="16" /></button>
          </header>

          <div class="scroll">
            <p v-if="av.error && !av.loaded" class="msg err" role="alert">
              {{ av.error }} <button class="link" @click="refrescarAvisos">Reintentar</button>
            </p>
            <div v-else-if="av.loading && !av.loaded" class="skels" aria-hidden="true"><i v-for="n in 4" :key="n" /></div>
            <p v-else-if="!av.items.length" class="msg">Todavía no hay avisos. Cuando una sesión te pregunte, termine o espere una aprobación, queda anotado acá.</p>

            <template v-else>
              <div v-for="g in grupos" :key="g.fecha" class="grp">
                <h3>{{ g.label }}</h3>
                <template v-for="a in g.items" :key="a.id">
                  <div
                    v-if="a.kind === 'pestana' && a.pedido && pedidoPestanaPendiente(a.pedido) && cardDeAviso(a)"
                    class="item pestana-fill"
                    :class="{ nuevo: a.id > av.nuevosDesde }"
                  >
                    <PedidoPestanaCard
                      :pedido="cardDeAviso(a)!"
                      :busy="!!pedidosPestana.porId[a.pedido]?.enviando"
                      :error="pedidosPestana.porId[a.pedido]?.error"
                      :vista="pedidosPestana.porId[a.pedido]?.vista"
                      @abrir="abrirPedidoPestana"
                      @rechazar="rechazarPedidoPestana"
                    />
                  </div>
                  <button
                    v-else
                    class="item"
                    :class="[`k-${a.kind}`, { nuevo: a.id > av.nuevosDesde, acento: kindsAcento.includes(a.kind) }]"
                    @click="tocar(a)"
                  >
                    <span class="ico" aria-hidden="true"><Icon :name="iconoAviso(a.kind, avisosDePiezas)" :size="15" /></span>
                    <span class="txt">
                      <span class="line">
                        <b class="tit">{{ a.titulo }}</b>
                        <time>{{ horaDeAviso(a.ts) }}</time>
                      </span>
                      <span v-if="a.cuerpo" class="body">{{ a.cuerpo }}</span>
                      <span v-if="!a.entregado" class="meta">
                        <i class="off">{{ a.motivo === "en la app" ? "Estabas en la app" : "No llegó al celu" }}</i>
                      </span>
                    </span>
                  </button>
                </template>
              </div>
              <button v-if="av.hayMas" class="more" :disabled="av.loadingMore" @click="masAvisos">{{ av.loadingMore ? 'Cargando…' : 'Ver más antiguos' }}</button>
            </template>
          </div>
        </section>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.bell { position: relative; width: 32px; height: 32px; display: grid; place-items: center; border-radius: var(--r-md); color: var(--text-2); border: 1px solid var(--line); transition: background 0.2s, color 0.2s, scale 0.3s var(--spring), border-color 0.2s; }
.bell:hover { background: var(--surface-hover); color: var(--text); border-color: var(--line-2); }
.bell:active { scale: var(--press-scale); }
.pip { position: absolute; top: -3px; right: -3px; min-width: 17px; height: 17px; padding: 0 4px; border-radius: var(--r-md); display: grid; place-items: center; font-size: var(--t-xs); font-weight: 700; line-height: 1; background: var(--accent); color: var(--accent-ink); box-shadow: 0 0 0 2px var(--bg), 0 0 10px -1px var(--accent); }
.pip-enter-active { transition: transform 0.5s var(--spring), opacity 0.2s; }
.pip-leave-active { transition: transform 0.15s, opacity 0.15s; }
.pip-enter-from, .pip-leave-to { transform: scale(0.3); opacity: 0; }
.av { position: fixed; inset: 0; z-index: 58; display: flex; align-items: flex-end; justify-content: center; }
.back { position: absolute; inset: 0; background: rgb(6 8 7 / 0.55); }
:root[data-theme='light'] .back { background: rgb(30 34 30 / 0.35); }
.wide .back { background: transparent; }
.panel { position: relative; width: min(100%, 560px); max-height: min(82dvh, 100%); display: flex; flex-direction: column; border-radius: 20px 20px 0 0; background: var(--surface); border: 1px solid var(--line-2); border-bottom: 0; box-shadow: var(--shadow-pop); outline: none; overflow: hidden; padding-bottom: env(safe-area-inset-bottom); }
.wide .panel { position: fixed; width: 420px; max-height: min(72vh, 640px); border-radius: 16px; border-bottom: 1px solid var(--line-2); padding-bottom: 0; transform-origin: top right; }
.grip { display: block; width: 38px; height: 4px; border-radius: 4px; margin: 10px auto 2px; background: var(--line-2); flex: none; }
.wide .grip { display: none; }
.top { display: flex; align-items: center; gap: 8px; padding: 10px 14px 10px 18px; flex: none; border-bottom: 1px solid var(--line); }
h2 { display: flex; align-items: center; gap: 8px; margin: 0 auto 0 0; font-family: var(--font-display); font-size: 17px; font-weight: 600; letter-spacing: -0.02em; }
h2 :deep(svg) { color: var(--accent); }
.mark { display: inline-flex; align-items: center; gap: 5px; height: 30px; padding: 0 11px; border-radius: var(--r-pill); font-size: 12px; font-weight: 600; color: var(--accent); background: var(--accent-soft); transition: filter 0.2s, scale 0.3s var(--spring); }
.mark:hover { filter: brightness(1.1); }
.mark:active { scale: var(--press-scale); }
.x { width: 32px; height: 32px; display: grid; place-items: center; border-radius: 50%; color: var(--text-3); transition: background 0.2s, color 0.2s; }
.x:hover { background: var(--surface-hover); color: var(--text); }
.scroll { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 4px 8px 14px; }
.grp h3 { position: sticky; top: 0; z-index: 1; margin: 0; padding: 12px 10px 6px; font-size: 11px; font-weight: 600; letter-spacing: 0.09em; text-transform: uppercase; color: var(--text-4); background: linear-gradient(var(--surface) 70%, transparent); }
.item { display: flex; align-items: flex-start; gap: 11px; width: 100%; padding: 11px 10px; border-radius: var(--r-lg); text-align: left; position: relative; transition: background 0.2s, scale 0.3s var(--spring); }
.pestana-fill { display: block; padding: 12px 12px 14px; border: 1px solid var(--line); background: var(--surface-2); }
.item:hover { background: var(--surface-hover); }
.item:active { scale: 0.985; }
.ico { position: relative; flex: none; width: 32px; height: 32px; display: grid; place-items: center; border-radius: var(--r-md); color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
.item.nuevo .ico::after { content: ''; position: absolute; top: -2px; right: -2px; width: 8px; height: 8px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 2px var(--surface), 0 0 8px var(--accent); }
.k-asks .ico { color: var(--st-working); background: var(--st-working-soft); box-shadow: none; }
.k-blocked .ico { color: var(--st-blocked); background: var(--st-blocked-soft); box-shadow: none; }
.k-done .ico { color: var(--st-done); background: var(--st-done-soft); box-shadow: none; }
.acento .ico { color: var(--accent); background: var(--accent-soft); box-shadow: none; }
.txt { min-width: 0; flex: 1; display: grid; gap: 3px; }
.line { display: flex; align-items: baseline; gap: 8px; }
.tit { min-width: 0; flex: 1; font-size: 14px; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.line time { flex: none; font-size: var(--t-sm); color: var(--text-3); white-space: nowrap; font-variant-numeric: tabular-nums; }
.body { font-size: 13px; line-height: 1.4; color: var(--text-2); display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
.meta { display: flex; gap: 6px; flex-wrap: wrap; }
.meta .off { font-style: normal; font-size: 11px; color: var(--text-3); }
.msg { margin: 0; padding: 26px 18px; text-align: center; font-size: var(--t-lg); line-height: 1.5; color: var(--text-3); }
.msg.err { color: var(--danger); }
.link { font-weight: 600; color: var(--accent); }
.skels { display: grid; gap: 10px; padding: 12px 10px; }
.skels i { display: block; height: 52px; border-radius: var(--r-lg); background: var(--surface-2); animation: pulse 1.4s ease-in-out infinite; }
@keyframes pulse { 50% { opacity: 0.5; } }
.more { display: block; margin: 8px auto 0; height: 36px; padding: 0 16px; border-radius: var(--r-pill); font-size: 13px; font-weight: 560; color: var(--text-2); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line-2); }
.more:disabled { opacity: 0.6; }
.av-enter-active .panel { transition: transform 0.55s var(--spring), opacity 0.25s; }
.av-enter-active .back, .av-leave-active .back { transition: opacity 0.25s; }
.av-leave-active .panel { transition: transform 0.25s var(--ease-in-out), opacity 0.2s; }
.av-enter-from .back, .av-leave-to .back { opacity: 0; }
.av-enter-from .panel, .av-leave-to .panel { transform: translateY(100%); }
.wide.av-enter-from .panel, .wide.av-leave-to .panel { transform: translateY(-8px) scale(0.96); opacity: 0; }
:root[data-motion='soft'] .av-enter-active .panel, :root[data-motion='soft'] .av-leave-active .panel { transition: opacity 0.15s; }
:root[data-motion='soft'] .av-enter-from .panel, :root[data-motion='soft'] .av-leave-to .panel { transform: none; opacity: 0; }
</style>

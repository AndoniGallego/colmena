<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useFocusTrap } from '../lib/focusTrap'
import { renderMarkdown } from '../lib/markdown'
import { desktop } from '../lib/viewport'
import { abrirRegla, arreglar, cargarKit, cerrarRegla, closeKit, kit } from '../state/kit'
import Icon from './Icon.vue'
import InlineAlert from './InlineAlert.vue'
import ViewFrame from './ViewFrame.vue'

const frame = ref<{ $el: HTMLElement } | null>(null)
const panel = computed(() => frame.value?.$el ?? null)
const backBtn = ref<HTMLButtonElement | null>(null)

function atras() {
  if (kit.regla) cerrarRegla()
  else closeKit()
}

const { onKeydown } = useFocusTrap(panel, () => true, { onEscape: atras, initial: () => backBtn.value })

const html = computed(() => (kit.regla?.texto ? renderMarkdown(kit.regla.texto) : ''))

onMounted(() => void cargarKit())
</script>

<template>
  <ViewFrame
    ref="frame"
    class="kv"
    :class="{ desk: desktop }"
    role="dialog"
    aria-modal="true"
    aria-label="Kit"
    tabindex="-1"
    title="Kit"
    sticky-head
    show-back
    :back-icon="desktop ? 'close' : 'back'"
    :back-label="desktop ? 'Cerrar Kit' : 'Volver'"
    @back="closeKit"
    @keydown="onKeydown"
  >
    <template #back>
      <button ref="backBtn" type="button" class="btn btn-back btn-icon" :class="{ 'btn-back--wide': desktop }" :aria-label="desktop ? 'Cerrar Kit' : 'Volver'" @click="closeKit">
        <Icon :name="desktop ? 'close' : 'back'" :size="18" />
        <span v-if="desktop" class="esc mono">Esc</span>
      </button>
    </template>

    <div class="kv-body">
      <section v-if="kit.regla" class="kv-regla" aria-live="polite">
        <button type="button" class="btn btn-ghost kv-volver hit" data-test="volver-regla" @click="cerrarRegla">
          <Icon name="back" :size="14" /><span>Todas las reglas</span>
        </button>
        <h2 class="kv-rtitulo">{{ kit.regla.titulo }}</h2>
        <p v-if="kit.regla.cargando" class="kv-mudo" role="status">Leyendo la regla…</p>
        <InlineAlert v-else-if="kit.regla.error">{{ kit.regla.error }}</InlineAlert>
        <!-- eslint-disable-next-line vue/no-v-html -- renderMarkdown sanitiza con DOMPurify -->
        <div v-else class="md kv-texto ui-card" data-test="regla-texto" v-html="html" />
      </section>

      <template v-else>
        <InlineAlert v-if="kit.error && !kit.data">
          {{ kit.error }}
          <template #action>
            <button type="button" class="btn btn-ghost hit" data-test="reintentar" @click="cargarKit">Reintentar</button>
          </template>
        </InlineAlert>
        <p v-else-if="!kit.data" class="kv-mudo" role="status">Revisando el kit…</p>

        <template v-if="kit.data">
          <section class="ui-card kv-estado" :class="kit.data.estado.al_dia ? 'ok' : 'mal'" data-test="estado" aria-live="polite">
            <div class="kv-estado-top">
              <span class="kv-sello" aria-hidden="true"><Icon :name="kit.data.estado.al_dia ? 'check' : 'warn'" :size="16" /></span>
              <div class="kv-estado-txt">
                <strong>{{ kit.data.estado.al_dia ? 'Kit al día' : 'El kit necesita un arreglo' }}</strong>
                <span v-if="kit.data.estado.al_dia" class="kv-mudo">Todo está instalado como tiene que estar.</span>
                <span v-else class="kv-mudo">Esto es lo que no coincide:</span>
              </div>
              <button v-if="!kit.data.estado.al_dia" type="button" class="btn btn-primary kv-arreglar hit" data-test="arreglar" :disabled="kit.arreglando" :aria-busy="kit.arreglando" @click="arreglar">
                {{ kit.arreglando ? 'Arreglando…' : 'Arreglar' }}
              </button>
            </div>
            <ul v-if="kit.data.estado.problemas.length" class="kv-problemas">
              <li v-for="p in kit.data.estado.problemas" :key="p">{{ p }}</li>
            </ul>
            <InlineAlert v-if="kit.errorArreglo">{{ kit.errorArreglo }}</InlineAlert>
          </section>

          <section class="kv-sec" aria-labelledby="kv-reglas">
            <h2 id="kv-reglas" class="kv-h">Reglas</h2>
            <p class="kv-sub">Lo que cada sesión de Claude tiene que cumplir. Tocá una para leerla entera.</p>
            <ul class="kv-lista ui-card">
              <li v-for="r in kit.data.reglas" :key="r.id">
                <button type="button" class="kv-fila hit" data-test="regla" @click="abrirRegla(r)">
                  <span class="kv-fila-txt"><strong>{{ r.titulo }}</strong><span>{{ r.proposito }}</span></span>
                  <Icon name="chevron" :size="14" />
                </button>
              </li>
            </ul>
          </section>

          <section class="kv-sec" aria-labelledby="kv-skills">
            <h2 id="kv-skills" class="kv-h">Skills</h2>
            <p class="kv-sub">Capacidades que Claude carga cuando hacen falta.</p>
            <ul class="kv-lista ui-card">
              <li v-for="s in kit.data.skills" :key="s.id" class="kv-item">
                <strong>{{ s.nombre }}</strong><span>{{ s.que_hace }}</span>
              </li>
            </ul>
          </section>

          <section class="kv-sec" aria-labelledby="kv-hooks">
            <h2 id="kv-hooks" class="kv-h">Hooks</h2>
            <p class="kv-sub">Controles automáticos que corren solos en cada sesión.</p>
            <ul class="kv-lista ui-card">
              <li v-for="h in kit.data.hooks" :key="h.id" class="kv-item">
                <strong class="mono">{{ h.nombre }}</strong><span>{{ h.que_hace }}</span>
              </li>
            </ul>
          </section>
        </template>
      </template>
    </div>
  </ViewFrame>
</template>

<style scoped>
.kv {
  position: fixed;
  inset: 0;
  z-index: 80;
  background-image: radial-gradient(1000px 420px at 0% -10%, var(--accent-soft), transparent 60%);
  outline: none;
  overflow: hidden;
}
.kv :deep(.vf-body) {
  flex: 1;
  min-height: 0;
  padding: 0;
  gap: 0;
  overflow: hidden;
}
.kv-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  padding: var(--view-pad-top) var(--gutter) calc(40px + env(safe-area-inset-bottom));
  padding-left: max(var(--gutter), env(safe-area-inset-left));
  padding-right: max(var(--gutter), env(safe-area-inset-right));
  display: grid;
  gap: 20px;
  max-width: var(--read-max);
  width: 100%;
  margin: 0 auto;
  align-content: start;
}
.desk .kv-body {
  padding-top: 28px;
}
.kv-mudo {
  margin: 0;
  color: var(--text-3, var(--text-2));
  font-size: 13px;
}
.kv-estado {
  padding: 14px;
  display: grid;
  gap: 10px;
}
.kv-estado-top {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}
.kv-estado-txt {
  flex: 1;
  min-width: 0;
  display: grid;
  gap: 2px;
}
.kv-sello {
  flex: none;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: grid;
  place-items: center;
}
.ok .kv-sello {
  background: var(--st-done-soft);
  color: var(--st-done);
}
.mal .kv-sello {
  background: var(--danger-soft);
  color: var(--danger);
}
.kv-arreglar {
  flex: none;
}
.kv-problemas {
  margin: 0;
  padding-left: 1.2em;
  display: grid;
  gap: 4px;
  font-size: 14px;
  color: var(--text-2);
}
.kv-sec {
  display: grid;
  gap: 6px;
}
.kv-h {
  margin: 0;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 620;
}
.kv-sub {
  margin: 0 0 4px;
  font-size: 13px;
  color: var(--text-3, var(--text-2));
}
.kv-lista {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow: hidden;
}
.kv-lista > li + li {
  border-top: 1px solid var(--line);
}
.kv-fila {
  width: 100%;
  min-height: 52px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  text-align: left;
  color: var(--text-2);
}
.kv-fila:hover {
  background: var(--surface-2);
}
.kv-fila-txt,
.kv-item {
  display: grid;
  gap: 2px;
  min-width: 0;
  flex: 1;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.kv-item {
  padding: 10px 14px;
  color: var(--text-2);
}
.kv-fila-txt strong,
.kv-item strong {
  color: var(--text);
  font-size: 14px;
}
.kv-regla {
  display: grid;
  gap: 12px;
  align-content: start;
}
.kv-volver {
  justify-self: start;
}
.kv-rtitulo {
  margin: 0;
  font-family: var(--font-display);
  font-size: 19px;
  font-weight: 620;
  text-wrap: balance;
}
.kv-texto {
  padding: 14px 16px;
  font-size: 14px;
  line-height: 1.55;
}
</style>

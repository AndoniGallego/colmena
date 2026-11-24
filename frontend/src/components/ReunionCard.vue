<script setup lang="ts">
import { ref, watch } from 'vue'
import { ApiError } from '../api/types'
import { duracionLabel, MOTIVO_LABEL, type ReunionGuardada } from '../lib/reunion'
import { getLibraryCharla } from '../state/app'

const props = defineProps<{
  data: ReunionGuardada
  itemId: string
  /** La charla sigue en disco; se borra a los 90 días. */
  tieneCharla: boolean
}>()

const charla = ref<string | null>(null)
const cargando = ref(false)
const error = ref(false)
const borrada = ref(false)
let seq = 0

watch(() => props.itemId, () => {
  seq++
  borrada.value = false
  charla.value = null
  cargando.value = false
  error.value = false
})

async function verCharla() {
  if (cargando.value) return
  const mine = ++seq
  cargando.value = true
  error.value = false
  try {
    const t = await getLibraryCharla(props.itemId)
    if (mine === seq) charla.value = t
  } catch (e) {
    if (mine === seq) {
      if (e instanceof ApiError && e.status === 404) borrada.value = true
      else error.value = true
    }
  } finally {
    if (mine === seq) cargando.value = false
  }
}
</script>

<template>
  <article class="reunion" :aria-label="`Reunión: ${data.titulo}`">
    <header class="cab">
      <span class="ico" aria-hidden="true">🎙️</span>
      <h3 class="tit">{{ data.titulo }}</h3>
    </header>
    <dl class="datos">
      <div><dt>Duración</dt><dd class="mono">{{ duracionLabel(data.duracion_s) }}</dd></div>
      <div><dt>Inicio</dt><dd class="mono">{{ data.inicio }}</dd></div>
      <div><dt>Fin</dt><dd class="mono">{{ data.fin }}</dd></div>
      <div class="ancho"><dt>Cómo terminó</dt><dd>{{ MOTIVO_LABEL[data.motivo] }}</dd></div>
    </dl>
    <ul v-if="data.repos.length" class="repos" aria-label="Repos">
      <li v-for="r in data.repos" :key="r" class="mono">{{ r }}</li>
    </ul>

    <section v-if="data.resumen.length" class="bloque">
      <h4>Resumen</h4>
      <ul class="puntos">
        <li v-for="(t, i) in data.resumen" :key="i">{{ t }}</li>
      </ul>
    </section>
    <section v-if="data.pendientes.length" class="bloque">
      <h4>Pendientes</h4>
      <ul class="puntos">
        <li v-for="(t, i) in data.pendientes" :key="i">{{ t }}</li>
      </ul>
    </section>
    <section v-if="data.tocadas.length" class="bloque">
      <h4>Lo que se tocó</h4>
      <ul class="tocadas">
        <li v-for="(t, i) in data.tocadas" :key="i" class="tocada">
          <p class="texto"><b v-if="t.tipo" class="tipo mono">{{ t.tipo }}</b>{{ t.texto }}</p>
          <p v-if="t.respuesta" class="respuesta"><span>Respuesta</span>{{ t.respuesta }}</p>
          <p v-if="t.archivos.length" class="archivos mono">{{ t.archivos.join(' · ') }}</p>
        </li>
      </ul>
    </section>

    <section class="bloque charla">
      <h4>Charla</h4>
      <p v-if="!tieneCharla || borrada" class="vacio">La charla ya se borró (pasaron 90 días)</p>
      <template v-else>
        <button v-if="charla === null" type="button" class="btn" :disabled="cargando" @click="verCharla">
          {{ cargando ? 'Cargando…' : 'Ver la charla' }}
        </button>
        <p v-if="error" class="vacio" role="alert">No pude traer la charla. Probá de nuevo.</p>
        <pre v-if="charla !== null" class="pre mono" tabindex="0" aria-label="Charla completa">{{ charla }}</pre>
      </template>
    </section>
  </article>
</template>

<style scoped>
.reunion {
  display: grid;
  gap: 14px;
  max-width: 820px;
  margin: 0 auto;
  padding: 14px;
  min-width: 0;
  border-radius: var(--r-lg);
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
}
.cab {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.tit {
  margin: 0;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.015em;
  text-wrap: balance;
  overflow-wrap: anywhere;
}
.datos {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px 14px;
  margin: 0;
}
.datos div {
  min-width: 0;
}
.datos .ancho {
  grid-column: 1 / -1;
}
dt {
  font-size: 11px;
  color: var(--text-3);
}
dd {
  margin: 1px 0 0;
  font-size: 13px;
  color: var(--text);
  overflow-wrap: anywhere;
}
.repos {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.repos li {
  padding: 2px 9px;
  border-radius: var(--r-pill);
  font-size: 11px;
  color: var(--text-2);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  overflow-wrap: anywhere;
}
.bloque h4 {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-3);
}
.puntos,
.tocadas {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.puntos li {
  position: relative;
  padding-left: 16px;
  font-size: 14px;
  line-height: 1.5;
  text-wrap: pretty;
  overflow-wrap: anywhere;
}
.puntos li::before {
  content: '';
  position: absolute;
  left: 3px;
  top: 0.62em;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--accent);
}
.tocada {
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
  min-width: 0;
}
.tocada p {
  margin: 0;
  font-size: 13px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.tipo {
  margin-right: 8px;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  font-size: 10px;
  font-weight: 500;
  color: var(--accent);
  background: var(--accent-soft);
}
.respuesta {
  margin-top: 4px !important;
  color: var(--text-2);
}
.respuesta span {
  margin-right: 6px;
  font-size: 11px;
  color: var(--text-3);
}
.archivos {
  margin-top: 4px !important;
  font-size: 11px !important;
  color: var(--text-3);
}
.vacio {
  margin: 0;
  font-size: 13px;
  color: var(--text-2);
}
.btn {
  display: inline-flex;
  align-items: center;
  min-height: 44px;
  padding: 0 18px;
  border-radius: var(--r-pill);
  font-size: var(--t-lg);
  color: var(--text);
  box-shadow: inset 0 0 0 1px var(--line-2);
  touch-action: manipulation;
  transition: background 0.2s, box-shadow 0.2s, scale 0.3s var(--spring);
}
.btn:active {
  scale: var(--press-scale);
}
.btn:disabled {
  opacity: 0.6;
}
.btn:focus-visible,
.pre:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
@media (hover: hover) and (pointer: fine) {
  .btn:hover {
    background: var(--surface-hover);
    box-shadow: inset 0 0 0 1px var(--accent-line);
  }
}
.pre {
  margin: 0;
  max-height: min(60dvh, 520px);
  padding: 12px;
  overflow: auto;
  overscroll-behavior: contain;
  font-size: 12px;
  line-height: 1.55;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
@media (max-width: 519px) {
  .datos {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .reunion {
    padding: 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .btn {
    transition: none;
  }
}
</style>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { conteo, type CasoPrueba, type Pruebas } from '../lib/pruebas'
import { cachedLibItem, fresh } from '../state/biblioteca'
const FotoCarrusel = defineAsyncComponent(() => import('./FotoCarrusel.vue'))

const props = defineProps<{
  data: Pruebas
  /** ruta de la captura -> id de la Biblioteca */
  evidencias?: Record<string, string>
}>()

const MARCA = { ok: '✓', falla: '✗', omitida: '–' } as const
const urls = ref<Record<string, string>>({})
const abierta = ref<string | null>(null)
const ancla = ref<HTMLElement | null>(null)

const cuenta = computed(() => {
  const c = conteo(props.data)
  return (['ok', 'falla', 'omitida'] as const).filter((k) => c[k] > 0).map((k) => `${c[k]} ${k}`)
})

const idDe = (c: CasoPrueba) => (c.evidencia ? props.evidencias?.[c.evidencia] : undefined)
const archivo = (ruta: string) => ruta.split('/').filter(Boolean).pop() ?? ruta

watch(
  () => [props.data, props.evidencias],
  async () => {
    for (const c of props.data.casos) {
      const id = idDe(c)
      if (!id || urls.value[id]) continue
      const item = await cachedLibItem(id)
      if (!item) continue
      const ready = await fresh(item)
      if (ready.src) urls.value = { ...urls.value, [id]: ready.src }
    }
  },
  { immediate: true },
)

function abrir(id: string, el: HTMLElement) {
  ancla.value = el
  abierta.value = id
}
</script>

<template>
  <section class="pruebas ui-card" :aria-label="`Pruebas: ${data.titulo}`">
    <header class="cab">
      <span class="ico" aria-hidden="true">🧪</span>
      <h3 class="tit">{{ data.titulo }}</h3>
      <span v-if="cuenta.length" class="cuenta mono">{{ cuenta.join(' · ') }}</span>
    </header>
    <p v-if="data.resumen" class="resumen">{{ data.resumen }}</p>
    <ul class="casos">
      <li v-for="(c, i) in data.casos" :key="i" class="caso" :data-res="c.resultado">
        <span class="marca" aria-hidden="true">{{ MARCA[c.resultado] }}</span>
        <div class="cuerpo">
          <span class="nombre">{{ c.nombre }}</span>
          <span class="sr-only"> ({{ c.resultado }})</span>
          <p v-if="c.detalle" class="detalle">{{ c.detalle }}</p>
          <template v-if="c.evidencia">
            <button
              v-if="idDe(c)"
              type="button"
              class="captura"
              @click="abrir(idDe(c)!, $event.currentTarget as HTMLElement)"
            >
              <img v-if="urls[idDe(c)!]" :src="urls[idDe(c)!]" alt="" loading="lazy" decoding="async" />
              <span>captura</span>
            </button>
            <span v-else class="ruta mono">{{ archivo(c.evidencia) }}</span>
          </template>
        </div>
      </li>
    </ul>
    <FotoCarrusel v-if="abierta" :fotos="[{ id: abierta }]" :start="0" :from="ancla" @close="abierta = null" />
  </section>
</template>

<style scoped>
.pruebas {
  padding: 10px 12px;
  min-width: 0;
  background: var(--surface-2);
}
.cab {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
}
.tit {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  min-width: 0;
  overflow-wrap: anywhere;
}
.cuenta {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-2);
}
.resumen {
  margin: 6px 0 0;
  font-size: 13px;
  color: var(--text-2);
  overflow-wrap: anywhere;
}
.casos {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.caso {
  display: flex;
  gap: 8px;
  min-width: 0;
}
.marca {
  flex: none;
  width: 1.2em;
  text-align: center;
  font-weight: 700;
  color: var(--accent);
}
.cuerpo {
  min-width: 0;
  font-size: 13px;
  overflow-wrap: anywhere;
}
.detalle {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--text-2);
}
.caso[data-res='falla'] .marca,
.caso[data-res='falla'] .nombre {
  color: var(--danger);
}
.caso[data-res='falla'] .nombre {
  font-weight: 600;
}
.caso[data-res='omitida'] {
  opacity: 0.6;
}
.caso[data-res='omitida'] .marca {
  color: var(--text-3);
}
.captura {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  padding: 2px 8px 2px 2px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: transparent;
  color: var(--text-2);
  font-size: 12px;
  cursor: pointer;
}
.captura img {
  width: 44px;
  height: 32px;
  object-fit: cover;
  border-radius: 6px;
}
.ruta {
  display: block;
  margin-top: 3px;
  font-size: 11px;
  color: var(--text-3);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
}
</style>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { DecisionPropuesta, Propuesta, ResumenSemanal } from '../api/types'
import { detalleDe, seccionesDe } from '../lib/resumen'
import { marcarPropuesta } from '../state/app'
import { briefPropuesta } from '../lib/briefPropuesta'
import NuevaTerminalSheet from './NuevaTerminalSheet.vue'

const props = defineProps<{
  data: ResumenSemanal
  itemId: string
}>()
const emit = defineEmits<{ hacer: [propuesta: Propuesta] }>()

const DECISIONES: { valor: DecisionPropuesta; label: string; marca: string }[] = [
  { valor: 'hacer', label: 'Hacer', marca: 'hacer' },
  { valor: 'ignorar', label: 'Ignorar 30 días', marca: 'ignorar' },
  { valor: 'mas_adelante', label: 'Más adelante', marca: 'más adelante' },
]

const marcadas = reactive<Record<string, DecisionPropuesta>>({})
const fallaron = reactive<Record<string, boolean>>({})
const ocupadas = reactive<Record<string, boolean>>({})
const abiertas = ref<Record<string, boolean>>({})
const hojaAbierta = ref(false)
const brief = ref('')

watch(() => props.itemId, () => {
  for (const o of [marcadas, fallaron, ocupadas]) for (const k of Object.keys(o)) delete o[k]
  abiertas.value = {}
  hojaAbierta.value = false
})

const secciones = computed(() => seccionesDe(props.data))
const nuevas = computed(() => props.data.propuestas?.nuevas ?? [])
const pie = computed(() => props.data.propuestas?.mas_adelante ?? [])
const seguimiento = computed(() => props.data.propuestas?.seguimiento ?? [])
const rango = computed(() => [props.data.desde, props.data.hasta].filter(Boolean).join(' al '))
const marcaDe = (id: string) => DECISIONES.find((d) => d.valor === marcadas[id])?.marca ?? ''

async function decidir(p: Propuesta, decision: DecisionPropuesta) {
  if (ocupadas[p.id]) return
  ocupadas[p.id] = true
  fallaron[p.id] = false
  try {
    await marcarPropuesta(p.id, decision)
    marcadas[p.id] = decision
    if (decision === 'hacer') {
      brief.value = briefPropuesta(p, props.data.semana)
      hojaAbierta.value = true
      emit('hacer', p)
    }
  } catch {
    fallaron[p.id] = true
  } finally {
    ocupadas[p.id] = false
  }
}

const alternar = (clave: string) => (abiertas.value = { ...abiertas.value, [clave]: !abiertas.value[clave] })
const TENDENCIA: Record<string, string> = { bajo: 'Bajó', subio: 'Subió', igual: 'Igual' }
</script>

<template>
  <article class="resumen" :aria-label="`Resumen de la semana ${data.semana}`">
    <header class="cab">
      <span class="ico" aria-hidden="true">📊</span>
      <h3 class="tit">Resumen de la semana</h3>
      <span v-if="rango" class="rango mono">{{ rango }}</span>
    </header>

    <section class="bloque" aria-label="Propuestas">
      <h4>Propuestas</h4>
      <p v-if="!nuevas.length" class="vacio">Esta semana no hay nada para proponer</p>
      <ul v-else class="props">
        <li v-for="p in nuevas" :key="p.id" class="propuesta">
          <p class="texto">
            <b v-if="p.volvio" class="volvio mono">Volvió</b>{{ p.texto }}
          </p>
          <div class="botones" role="group" :aria-label="`Qué hacer con: ${p.texto}`">
            <button
              v-for="d in DECISIONES"
              :key="d.valor"
              type="button"
              class="decision"
              :class="{ marcado: marcadas[p.id] === d.valor }"
              :aria-pressed="marcadas[p.id] === d.valor ? 'true' : 'false'"
              :disabled="ocupadas[p.id]"
              @click="decidir(p, d.valor)"
            >{{ d.label }}</button>
          </div>
          <p v-if="marcadas[p.id]" class="marca" role="status">Marcada: {{ marcaDe(p.id) }}</p>
          <p v-if="fallaron[p.id]" class="error" role="alert">No pude guardar la marca. Probá de nuevo.</p>
        </li>
      </ul>
    </section>

    <section class="bloque" aria-label="Números de la semana">
      <h4>La semana en números</h4>
      <ul class="secs">
        <li v-for="s in secciones" :key="s.clave" class="sec">
          <button
            type="button"
            class="sec-cab"
            :aria-expanded="abiertas[s.clave] ? 'true' : 'false'"
            :aria-controls="`sec-${itemId}-${s.clave}`"
            @click="alternar(s.clave)"
          >
            <span class="num mono">{{ s.numero }}</span>
            <span class="sec-txt"><b>{{ s.titulo }}</b><span class="frase">{{ s.frase }}</span></span>
            <i class="flecha" aria-hidden="true" />
          </button>
          <div v-if="abiertas[s.clave]" :id="`sec-${itemId}-${s.clave}`" class="sec-cuerpo">
            <template v-if="s.clave === 'errores'">
              <p v-if="!(data.resumen.errores?.top ?? []).length" class="vacio">Sin errores repetidos.</p>
              <ul v-else class="detalle">
                <li v-for="(e, i) in data.resumen.errores.top" :key="i">
                  <span class="mono">{{ e.tipo_exc }}</span> · {{ e.plantilla }}
                  <span class="chico">{{ e.n }} veces{{ e.hace ? `, ${e.hace}` : '' }}</span>
                </li>
              </ul>
            </template>
            <template v-else-if="s.clave === 'seguimiento'">
              <p v-if="!seguimiento.length" class="vacio">Nada en seguimiento.</p>
              <ul v-else class="detalle">
                <li v-for="x in seguimiento" :key="x.id">
                  {{ x.texto }}
                  <span class="chico">{{ TENDENCIA[x.tendencia ?? ''] ?? '' }}{{ x.base != null && x.valor != null ? ` (de ${x.base} a ${x.valor})` : '' }}</span>
                </li>
              </ul>
            </template>
            <dl v-else class="lineas">
              <div v-for="l in detalleDe(s.clave, data.resumen)" :key="l.etiqueta"><dt>{{ l.etiqueta }}</dt><dd class="mono">{{ l.valor }}</dd></div>
            </dl>
          </div>
        </li>
      </ul>
    </section>

    <section v-if="pie.length" class="bloque pie" aria-label="Para más adelante">
      <h4>Para más adelante</h4>
      <ul class="props">
        <li v-for="p in pie" :key="p.id" class="propuesta">
          <p class="texto">{{ p.texto }}</p>
          <div class="botones" role="group" :aria-label="`Qué hacer con: ${p.texto}`">
            <button
              v-for="d in DECISIONES"
              :key="d.valor"
              type="button"
              class="decision"
              :class="{ marcado: marcadas[p.id] === d.valor }"
              :aria-pressed="marcadas[p.id] === d.valor ? 'true' : 'false'"
              :disabled="ocupadas[p.id]"
              @click="decidir(p, d.valor)"
            >{{ d.label }}</button>
          </div>
          <p v-if="marcadas[p.id]" class="marca" role="status">Marcada: {{ marcaDe(p.id) }}</p>
          <p v-if="fallaron[p.id]" class="error" role="alert">No pude guardar la marca. Probá de nuevo.</p>
        </li>
      </ul>
    </section>

    <NuevaTerminalSheet :open="hojaAbierta" :tarea-inicial="brief" @close="hojaAbierta = false" />
  </article>
</template>

<style scoped>
.resumen {
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
  flex-wrap: wrap;
  align-items: baseline;
  gap: 4px 8px;
  min-width: 0;
}
.tit {
  margin: 0;
  font-family: var(--font-display);
  font-size: 17px;
  font-weight: 600;
  letter-spacing: -0.015em;
  text-wrap: balance;
}
.rango {
  font-size: 11px;
  color: var(--text-3);
}
.bloque {
  display: grid;
  gap: 8px;
  min-width: 0;
}
h4 {
  margin: 0;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--text-2);
}
ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}
.vacio {
  margin: 0;
  font-size: 13px;
  color: var(--text-2);
  text-wrap: pretty;
}
.propuesta {
  display: grid;
  gap: 8px;
  padding: 10px;
  min-width: 0;
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.texto {
  margin: 0;
  font-size: 14px;
  line-height: 1.45;
  text-wrap: pretty;
  overflow-wrap: anywhere;
}
.volvio {
  margin-right: 8px;
  padding: 1px 7px;
  border-radius: var(--r-pill);
  font-size: 10px;
  font-weight: 500;
  color: var(--accent);
  background: var(--accent-soft);
}
.botones {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.decision {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: 1 1 auto;
  min-height: 44px;
  padding: 0 14px;
  border-radius: var(--r-pill);
  font-size: 13px;
  color: var(--text);
  box-shadow: inset 0 0 0 1px var(--line-2);
  touch-action: manipulation;
  transition: background 0.2s, box-shadow 0.2s, color 0.2s, scale 0.3s var(--spring);
}
.decision:active:not(:disabled) {
  scale: var(--press-scale);
}
.decision:disabled {
  opacity: 0.6;
}
.decision.marcado {
  color: var(--accent-ink);
  background: var(--accent);
  box-shadow: none;
}
.decision:focus-visible,
.sec-cab:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
@media (hover: hover) and (pointer: fine) {
  .decision:hover:not(.marcado):not(:disabled),
  .sec-cab:hover {
    background: var(--surface-hover);
    box-shadow: inset 0 0 0 1px var(--accent-line);
  }
}
.marca {
  margin: 0;
  font-size: 12px;
  color: var(--accent);
}
.error {
  margin: 0;
  font-size: 12px;
  color: var(--danger);
}
.sec {
  min-width: 0;
  border-radius: var(--r-md);
  background: var(--surface);
  box-shadow: inset 0 0 0 1px var(--line);
}
.sec-cab {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  min-height: 56px;
  padding: 8px 12px;
  text-align: left;
  color: var(--text);
  border-radius: var(--r-md);
  touch-action: manipulation;
  transition: background 0.2s, box-shadow 0.2s;
}
.num {
  flex: none;
  min-width: 2ch;
  font-size: 26px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: -0.02em;
  font-variant-numeric: tabular-nums;
  color: var(--accent);
}
.sec-txt {
  display: grid;
  gap: 2px;
  flex: 1;
  min-width: 0;
  font-size: 14px;
}
.frase {
  font-size: 12px;
  line-height: 1.35;
  color: var(--text-2);
  text-wrap: pretty;
  overflow-wrap: anywhere;
}
.flecha {
  flex: none;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--text-3);
  border-bottom: 2px solid var(--text-3);
  rotate: 45deg;
  transition: rotate 0.25s var(--spring);
}
.sec-cab[aria-expanded='true'] .flecha {
  rotate: -135deg;
}
.sec-cuerpo {
  padding: 0 12px 12px;
  font-size: 13px;
  min-width: 0;
}
.detalle {
  gap: 6px;
}
.detalle li {
  line-height: 1.45;
  overflow-wrap: anywhere;
}
.lineas {
  display: grid;
  gap: 6px;
  margin: 0;
}
.lineas div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}
.lineas dt {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--text-2);
}
.lineas dd {
  margin: 0;
  flex: none;
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.chico {
  display: block;
  font-size: 11px;
  color: var(--text-3);
}
@media (max-width: 519px) {
  .resumen {
    padding: 12px;
  }
}
@media (prefers-reduced-motion: reduce) {
  .decision,
  .sec-cab,
  .flecha {
    transition: none;
  }
}
</style>

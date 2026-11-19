<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { Entorno, MetodoPrueba, PedidoPrueba, ResultadoPrueba } from '../api/entornosApi'
import { probarEntorno } from '../api/entornosApi'
import { ApiError } from '../api/types'
import { formatSize } from '../lib/attachments'
import { claseCodigo, cuerpoLegible, esMetodoQueCambia } from '../lib/entornos'

const props = defineProps<{
  entorno: Entorno
  probar?: (p: PedidoPrueba) => Promise<ResultadoPrueba>
}>()

const emit = defineEmits<{ cerrar: [] }>()

const METODOS: MetodoPrueba[] = ['GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE']

const abribles = computed(() => props.entorno.puertos.filter((p) => p.abrible))

function puertoInicial(): number {
  const pr = props.entorno.principal
  if (pr !== null) {
    const enc = props.entorno.puertos.find((p) => p.puerto === pr && p.abrible)
    if (enc) return pr
  }
  return abribles.value[0]?.puerto ?? 0
}

const puerto = ref(puertoInicial())
const metodo = ref<MetodoPrueba>('GET')
const ruta = ref('/')
const encabezados = ref<{ nombre: string; valor: string }[]>([])
const cuerpo = ref('')
const confirmando = ref(false)
const probando = ref(false)
const resultado = ref<ResultadoPrueba | null>(null)
const errorMsg = ref<string | null>(null)

const servicioSel = computed(
  () => abribles.value.find((p) => p.puerto === puerto.value)?.servicio ?? '',
)

const textoBoton = computed(() => {
  if (probando.value) return 'Probando…'
  if (confirmando.value && esMetodoQueCambia(metodo.value)) {
    return `Confirmar ${metodo.value} a ${servicioSel.value}`
  }
  return 'Enviar'
})

function reiniciarConfirmacion() {
  confirmando.value = false
}

watch([puerto, metodo, ruta, cuerpo], reiniciarConfirmacion)
watch(encabezados, reiniciarConfirmacion, { deep: true })

function agregarEncabezado() {
  encabezados.value.push({ nombre: '', valor: '' })
}

function quitarEncabezado(i: number) {
  encabezados.value.splice(i, 1)
}

async function enviar() {
  if (probando.value) return
  const cambia = esMetodoQueCambia(metodo.value)
  if (cambia && !confirmando.value) {
    confirmando.value = true
    return
  }
  probando.value = true
  errorMsg.value = null
  resultado.value = null
  const fn = props.probar ?? probarEntorno
  const cuerpoPedido =
    cambia && cuerpo.value.trim() !== '' ? cuerpo.value : null
  const pedido: PedidoPrueba = {
    nombre: props.entorno.nombre,
    puerto: puerto.value,
    metodo: metodo.value,
    ruta: ruta.value,
    encabezados: encabezados.value.filter((h) => h.nombre.trim() !== ''),
    cuerpo: cuerpoPedido,
    confirmado: cambia,
  }
  try {
    resultado.value = await fn(pedido)
  } catch (e) {
    errorMsg.value = e instanceof ApiError ? e.detail : String(e)
  } finally {
    probando.value = false
    confirmando.value = false
  }
}
</script>

<template>
  <section class="en-probador" aria-label="Probador de endpoints">
    <div class="pr-form">
      <div class="pr-field">
        <label for="pr-servicio">Servicio</label>
        <select id="pr-servicio" v-model.number="puerto">
          <option v-for="p in abribles" :key="p.puerto" :value="p.puerto">
            {{ p.servicio }} · {{ p.puerto }}
          </option>
        </select>
      </div>
      <div class="pr-field">
        <label for="pr-metodo">Método</label>
        <select id="pr-metodo" v-model="metodo">
          <option v-for="m in METODOS" :key="m" :value="m">{{ m }}</option>
        </select>
      </div>
      <div class="pr-field">
        <label for="pr-ruta">Ruta</label>
        <input id="pr-ruta" v-model="ruta" type="text" autocomplete="off" />
      </div>
      <div class="pr-enc">
        <span class="pr-enc-lab">Encabezados</span>
        <button type="button" class="btn btn-ghost btn-sm" @click="agregarEncabezado">Agregar encabezado</button>
        <div v-for="(h, i) in encabezados" :key="i" class="pr-enc-row">
          <label :for="`pr-hn-${i}`">Nombre</label>
          <input :id="`pr-hn-${i}`" v-model="h.nombre" type="text" autocomplete="off" />
          <label :for="`pr-hv-${i}`">Valor</label>
          <input :id="`pr-hv-${i}`" v-model="h.valor" type="text" autocomplete="off" />
          <button type="button" class="btn btn-ghost btn-sm" @click="quitarEncabezado(i)">Quitar</button>
        </div>
      </div>
      <div v-if="esMetodoQueCambia(metodo)" class="pr-field">
        <label for="pr-cuerpo">Cuerpo</label>
        <textarea id="pr-cuerpo" v-model="cuerpo" rows="4" />
      </div>
      <button type="button" class="btn btn-primary pr-enviar" :disabled="probando" @click="enviar">
        {{ textoBoton }}
      </button>
    </div>

    <div class="pr-salida" aria-live="polite">
      <div v-if="errorMsg" class="pr-error" role="alert">{{ errorMsg }}</div>
      <div v-if="resultado" class="pr-resultado">
        <p class="pr-meta">
          <span class="pr-codigo" :data-clase="claseCodigo(resultado.codigo)">{{ resultado.codigo }}</span>
          <span>{{ resultado.ms }} ms</span>
          <span>{{ formatSize(resultado.bytes) }}</span>
        </p>
        <p v-if="resultado.truncado">Respuesta cortada en 256 KB</p>
        <p v-if="resultado.cuerpo === null && resultado.bytes > 0">Contenido binario, no se muestra</p>
        <pre v-else-if="resultado.cuerpo !== null" class="pr-cuerpo">{{ cuerpoLegible(resultado.cuerpo) }}</pre>
        <details v-if="resultado.encabezados.length">
          <summary>Encabezados</summary>
          <ul>
            <li v-for="([n, v], j) in resultado.encabezados" :key="j">{{ n }}: {{ v }}</li>
          </ul>
        </details>
      </div>
    </div>

    <button type="button" class="btn btn-ghost pr-cerrar" @click="emit('cerrar')">Cerrar</button>
  </section>
</template>

<style scoped>
.en-probador {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  display: grid;
  gap: 12px;
}
.pr-form {
  display: grid;
  gap: 10px;
}
.pr-field {
  margin: 0;
  display: grid;
  gap: 4px;
  font-size: 13px;
}
.pr-field label,
.pr-enc-lab {
  font-weight: 540;
  color: var(--text-2);
}
.pr-field select,
.pr-field input,
.pr-field textarea,
.pr-enc-row input {
  width: 100%;
  font: inherit;
  font-size: 13px;
  padding: 8px 10px;
  border-radius: 8px;
  border: none;
  box-shadow: inset 0 0 0 1px var(--line);
  background: var(--surface-2);
  color: var(--text);
}
.pr-enc {
  display: grid;
  gap: 8px;
}
.pr-enc-row {
  display: grid;
  gap: 4px 8px;
  grid-template-columns: 1fr 1fr;
  align-items: center;
}
.pr-enc-row label {
  font-size: 12px;
  color: var(--text-3);
}
.pr-enviar {
  justify-self: start;
}
.pr-error {
  font-size: 13px;
  color: var(--danger);
  padding: 8px 10px;
  border-radius: 8px;
  background: color-mix(in srgb, var(--danger) 8%, var(--surface));
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 22%, var(--line));
}
.pr-resultado {
  display: grid;
  gap: 8px;
  font-size: 13px;
}
.pr-meta {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: baseline;
}
.pr-codigo {
  font-weight: 620;
  font-family: var(--font-mono);
}
.pr-codigo[data-clase='ok'] {
  color: var(--st-done);
}
.pr-codigo[data-clase='aviso'] {
  color: var(--st-blocked);
}
.pr-codigo[data-clase='mal'] {
  color: var(--danger);
}
.pr-cuerpo {
  margin: 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: var(--surface-2);
  box-shadow: inset 0 0 0 1px var(--line);
  font-size: 12px;
  line-height: 1.4;
  white-space: pre-wrap;
  word-break: break-word;
  overflow-x: auto;
  max-height: 50vh;
}
.pr-cerrar {
  justify-self: start;
}
</style>

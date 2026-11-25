<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import type { LineaReunion } from '../../state/reunion'
import {
  cargarNudo,
  cargarRepos,
  errorReunion,
  mirando,
  mostrarAhora,
  nudoPrendido,
  nuevaReunion,
  pausar,
  preguntarUltimo,
  puedeMostrar,
  repos,
  reunion,
  escuchar,
  seguir,
  terminar,
  tocar,
  descartar,
  anotar,
  guardarEnMemoria,
  guardandoMemoria,
} from '../../state/reunion'
import { abrirBiblioteca, abrirColmena } from '../../state/notch'
import { pcNudoActivo } from '../../state/app'

/** En la ventana aparte el panel llena el alto y solo la lista scrollea; en el notch sigue fluyendo. */
defineProps<{ ventana?: boolean }>()

onMounted(() => {
  if (!reunion.value.reunion) void cargarRepos()
  void cargarNudo()
})

const preguntaMostrar = ref('')
const mostrable = computed(() => puedeMostrar(e.value, nudoPrendido.value, mirando.value))
/** El motivo solo se muestra cuando el botón está apagado por una razón que el usuario puede cambiar. */
const motivoMostrar = computed(() => (mirando.value === null ? mostrable.value.motivo : undefined))

async function mostrarClick() {
  void cargarNudo()
  if (!mostrable.value.ok) return
  const p = preguntaMostrar.value.trim()
  await mostrarAhora(p)
  if (errorReunion.value === null) preguntaMostrar.value = ''
}

/** Repos que el Copiloto puede mirar; vacío significa "Todos". */
const elegidos = ref<string[]>([])
const todos = computed(() => elegidos.value.length === 0)
const ocupado = ref(false)

function alternarRepo(ruta: string) {
  const i = elegidos.value.indexOf(ruta)
  elegidos.value = i >= 0 ? elegidos.value.filter((r) => r !== ruta) : [...elegidos.value, ruta]
}

const tema = ref('')

/** Enter en el tema empieza, salvo mientras el IME está componiendo una palabra. */
function alEnterTema(ev: KeyboardEvent) {
  if (ev.isComposing || ev.keyCode === 229) return
  ev.preventDefault()
  void empezar()
}

async function empezar() {
  if (ocupado.value) return
  ocupado.value = true
  try {
    await escuchar(elegidos.value, todos.value, tema.value)
    if (errorReunion.value === null) tema.value = ''
  } finally {
    ocupado.value = false
  }
}

const e = computed(() => reunion.value)
const enCurso = computed(() => ['escuchando', 'pausada', 'sin_pc', 'llena', 'terminando'].includes(e.value.estado))
const terminada = computed(() => e.value.estado === 'guardada')
const sinTexto = computed(() => e.value.estado === 'escuchando' && e.value.sinTexto)
const cajitaAcoplada = computed(() => e.value.cajitaAcoplada && e.value.estado === 'escuchando')
const sinSubtitulos = computed(() => e.value.lector === 'sin_subtitulos' && e.value.estado === 'escuchando')
const pedirAMano = computed(() => e.value.estado !== 'terminando' && (e.value.tope || e.value.soloAMano))
const puedeTerminar = computed(() => ['escuchando', 'pausada', 'sin_pc', 'llena'].includes(e.value.estado))
const principal = computed(() => e.value.estado === 'llena')

const ETIQUETA: Record<string, string> = {
  escuchando: 'Escuchando',
  pausada: 'Pausada',
  sin_pc: 'Sin la PC',
  llena: 'Llena',
  terminando: 'Guardando',
  guardada: 'Guardada',
}
const etiqueta = computed(() => (sinSubtitulos.value ? 'Sin subtítulos' : (ETIQUETA[e.value.estado] ?? '')))

function verEnBiblioteca() {
  const id = e.value.biblioteca
  if (id) abrirBiblioteca(id)
  else abrirColmena()
}

const TIPO: Record<LineaReunion['tipo'], string> = { pregunta: 'Pregunta', requerimiento: 'Pedido', clave: 'Clave', manual: 'A mano', mostrar: 'Mostrame' }

const respondiendo = (l: LineaReunion) => l.respuesta?.estado === 'buscando' || l.respuesta?.estado === 'en_cola'
const conAcciones = (l: LineaReunion) => l.tipo !== 'mostrar'
const tocable = (l: LineaReunion) => l.tipo !== 'mostrar' && l.tipo !== 'clave' && (!l.respuesta || l.respuesta.estado === 'error')

/** El chip muestra el final de la ruta: lo que importa es el archivo, la ruta completa queda en el title. */
const corto = (ruta: string) => ruta.split('/').filter(Boolean).slice(-2).join('/') || ruta

/**
 * Las líneas nuevas entran arriba. Si el usuario está arriba de todo la lista las muestra;
 * si ya bajó a leer, se compensa el alto agregado para no arrastrarle la lectura.
 */
const scroller = ref<HTMLElement | null>(null)
const CERCA = 40
let altoPrevio = 0
watch(
  () => e.value.lineas.map((l) => l.id).join('|'),
  async () => {
    const el = scroller.value
    const antes = altoPrevio
    const arriba = !el || el.scrollTop <= CERCA
    const pos = el?.scrollTop ?? 0
    await nextTick()
    const d = scroller.value
    if (!d) return
    altoPrevio = d.scrollHeight
    if (arriba) d.scrollTop = 0
    else if (antes > 0 && d.scrollHeight > antes) d.scrollTop = pos + (d.scrollHeight - antes)
  },
)
watch(scroller, (el) => {
  altoPrevio = el?.scrollHeight ?? 0
})
</script>

<template>
  <section class="reunion" :class="{ 'en-ventana': ventana }" aria-label="Reunión">
    <header class="cab">
      <h3>Reunión</h3>
      <span v-if="etiqueta" class="estado" :class="`e-${sinSubtitulos ? 'sin_subtitulos' : e.estado}`" role="status">
        <span class="punto loop" aria-hidden="true" />{{ etiqueta }}
        <b v-if="enCurso && e.topeDetecciones > 0" class="cuenta" :title="'Detecciones de esta reunión'">{{ e.detecciones }}/{{ e.topeDetecciones }}</b>
      </span>
      <div v-if="enCurso" class="controles" role="group" aria-label="Controles de la reunión">
        <button v-if="e.estado === 'pausada'" type="button" class="suave ctl" @click="seguir()">Seguir</button>
        <button v-else type="button" class="suave ctl" :disabled="e.estado !== 'escuchando'" @click="pausar()">Pausar</button>
        <button type="button" class="terminar ctl" :class="{ principal }" :disabled="!puedeTerminar" @click="terminar()">Terminar</button>
      </div>
    </header>

    <!-- Sin reunión: elegir repos y empezar -->
    <div v-if="!enCurso && !terminada" class="elegir">
      <p class="rotulo">Repos que mira el Copiloto</p>
      <div class="chips" role="group" aria-label="Repos">
        <button type="button" class="chip" :class="{ on: todos }" :aria-pressed="todos" @click="elegidos = []">Todos</button>
        <button
          v-for="r in repos"
          :key="r.ruta"
          type="button"
          class="chip"
          :class="{ on: elegidos.includes(r.ruta) }"
          :aria-pressed="elegidos.includes(r.ruta)"
          :title="r.ruta"
          @click="alternarRepo(r.ruta)"
        >{{ r.nombre }}</button>
      </div>
      <label class="rotulo" for="reunion-tema">Tema (opcional)</label>
      <input
        id="reunion-tema"
        v-model="tema"
        type="text"
        class="tema-campo"
        maxlength="200"
        placeholder="De qué trata, para que el Copiloto arranque con contexto"
        enterkeyhint="go"
        autocomplete="off"
        @keydown.enter="alEnterTema"
      />
      <p class="ayuda">Abrí Subtítulos en vivo (Win+Ctrl+L) antes de empezar.</p>
      <button type="button" class="primario" :disabled="ocupado" @click="empezar">Escuchar</button>
    </div>

    <!-- Guardada -->
    <div v-else-if="terminada" class="cierre">
      <p class="aviso" role="status">Reunión guardada en la Biblioteca.</p>
      <div class="acciones">
        <button type="button" class="primario" @click="verEnBiblioteca">Ver en la Biblioteca</button>
        <button type="button" class="suave" @click="nuevaReunion()">Empezar otra</button>
      </div>
    </div>

    <!-- En curso -->
    <template v-else>
      <div class="extras">
      <p v-if="cajitaAcoplada" class="ayuda" role="status">Poné Subtítulos en "Superpuesto en la pantalla" para que no se vea al compartir</p>
      <p v-if="sinSubtitulos" class="aviso aviso-alerta" role="status">No encuentro los subtítulos: abrilos con Win+Ctrl+L</p>
      <p v-if="sinTexto" class="aviso aviso-alerta" role="status">Hace 2 minutos que no llega texto de los Subtítulos. Revisá que estén abiertos y mostrando lo que se dice.</p>
      <p v-if="e.estado === 'sin_pc'" class="aviso aviso-alerta" role="status">Perdí la conexión con la PC. Si no vuelve, guardo la reunión como quedó.</p>
      <p v-if="e.estado === 'llena'" class="aviso aviso-alerta" role="status">La charla llegó al largo máximo: tocá Terminar para guardarla.</p>
      <p v-if="e.estado === 'terminando'" class="aviso" role="status">Guardando la reunión…</p>
      <p v-if="e.copiloto === 'abriendo' && e.estado === 'escuchando'" class="nota">Abriendo el Copiloto…</p>
      <p v-else-if="e.copiloto === 'sin_copiloto'" class="aviso aviso-alerta" role="status">El Copiloto no abrió: no puedo responder las preguntas.</p>

      <div v-if="pedirAMano" class="tope">
        <p class="aviso" role="status">
          <template v-if="e.soloAMano">La detección automática está apagada: preguntá a mano.</template>
          <template v-else>Llegué al tope de detecciones de esta reunión.</template>
        </p>
        <button type="button" class="suave" @click="preguntarUltimo()">Preguntar por lo último</button>
      </div>

      <div v-if="pcNudoActivo && puedeTerminar" class="mostrar">
        <div class="mostrar-fila">
          <input
            v-model="preguntaMostrar"
            type="text"
            class="mostrar-campo"
            maxlength="300"
            placeholder="¿Qué querés que te muestre?"
            aria-label="¿Qué querés que te muestre?"
            enterkeyhint="send"
            autocomplete="off"
            spellcheck="false"
            @keydown.enter.prevent="mostrarClick"
          />
          <button type="button" class="suave mostrar-boton" :disabled="!mostrable.ok" @click="mostrarClick">
            <svg class="ojo" viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
              <path d="M1.5 8S3.8 3.5 8 3.5 14.5 8 14.5 8 12.2 12.5 8 12.5 1.5 8 1.5 8Z" />
              <circle cx="8" cy="8" r="2" />
            </svg>
            Mostrame
          </button>
        </div>
        <p v-if="mirando !== null" class="nota mirando loop" role="status">Mirando la ventana…</p>
        <p v-else-if="motivoMostrar" class="nota" role="status">{{ motivoMostrar }}</p>
      </div>
      </div>

      <div v-if="!e.lineas.length" class="vacio" role="status">
        <span class="onda" :class="{ quieta: e.estado === 'pausada' }" aria-hidden="true">
          <i /><i /><i />
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5.5 11.5a6.5 6.5 0 0 0 13 0M12 18v3" />
          </svg>
        </span>
        <p class="vacio-titulo">{{ e.estado === 'pausada' ? 'En pausa' : 'Escuchando' }}</p>
        <p class="vacio-texto">{{ e.estado === 'pausada' ? 'Tocá Seguir para retomar la escucha.' : 'Las preguntas que detecte aparecen acá.' }}</p>
      </div>
      <div v-else ref="scroller" class="scroll">
        <TransitionGroup name="lin" tag="ul" class="lista">
          <li v-for="l in e.lineas" :key="l.id" class="linea" :class="{ hay: !!l.respuesta, 'con-acc': conAcciones(l) }">
            <button type="button" class="texto" :disabled="!tocable(l)" :aria-label="`${TIPO[l.tipo]}: ${l.texto}`" @click="tocar(l.id)">
              <span class="tipo" :class="`t-${l.tipo}`">{{ TIPO[l.tipo] }}</span>
              <span class="cuerpo">{{ l.texto }}</span>
            </button>
            <div v-if="conAcciones(l)" class="acc-grupo">
              <button v-if="!l.nota" type="button" class="acc" aria-label="Anotar" title="Anotar" @click.stop="anotar(l.id)">
                <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                  <path d="M9.5 2.5 13.5 6.5 11 9l-.5 3.5-7-7L7 5 9.5 2.5Z" />
                  <path d="M5 11 2.5 13.5" />
                </svg>
              </button>
              <button
                type="button"
                class="acc"
                aria-label="Descartar"
                title="Descartar"
                :disabled="l.respuesta?.estado === 'buscando'"
                @click.stop="descartar(l.id)"
              >
                <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" aria-hidden="true">
                  <path d="M4 4 12 12M12 4 4 12" />
                </svg>
              </button>
            </div>
            <div v-if="l.nota" class="fila-nota">
              <p class="sello">Anotada</p>
              <span v-if="l.memoria" class="en-memoria" role="status">En tu memoria</span>
              <button
                v-else-if="e.memoriaTrabajo"
                type="button"
                class="acc mem"
                aria-label="Guardar en mi memoria de trabajo"
                title="Guardar en mi memoria de trabajo"
                :disabled="guardandoMemoria.includes(l.id)"
                @click.stop="guardarEnMemoria(l.id)"
              >
                Guardar en mi memoria
              </button>
            </div>
            <p v-if="l.respuesta && respondiendo(l)" class="resp espera loop" role="status">
              {{ l.respuesta.estado === 'buscando' ? 'buscando…' : 'en cola…' }}
            </p>
            <p v-else-if="l.respuesta?.estado === 'error'" class="resp mal" role="status">
              No pude responder. Tocá la línea para probar de nuevo.
            </p>
            <div v-else-if="l.respuesta" class="resp">
              <p class="resp-texto">{{ l.respuesta.texto }}</p>
              <ul v-if="l.respuesta.archivos.length" class="archivos" aria-label="Archivos">
                <li v-for="a in l.respuesta.archivos" :key="a" class="archivo" :title="a">{{ corto(a) }}</li>
              </ul>
            </div>
          </li>
        </TransitionGroup>
      </div>
    </template>

    <p v-if="errorReunion" class="error" role="alert">{{ errorReunion }}</p>
  </section>
</template>

<style scoped>
.reunion {
  display: grid;
  gap: 10px;
  padding: 4px 2px 2px;
}
button {
  touch-action: manipulation;
  -webkit-tap-highlight-color: transparent;
  font: inherit;
}
.reunion.en-ventana {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 8px;
  padding: 0;
}
.cab {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 8px 12px;
  padding: 8px 6px 0;
}
.en-ventana .cab {
  flex: none;
  padding: 10px 12px;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
  box-shadow: 0 1px 0 color-mix(in srgb, var(--text) 4%, transparent) inset;
}
.en-ventana .cab h3 {
  flex: 1 1 auto;
}
.en-ventana .controles {
  flex: 1 1 100%;
}
.en-ventana .ctl {
  flex: 1;
  height: 40px;
  font-size: var(--t-md);
}
.en-ventana .ctl::before {
  inset: -2px;
}
.extras {
  display: grid;
  gap: 10px;
}
.extras:empty {
  display: none;
}
.en-ventana .extras {
  flex: none;
  max-height: 40%;
  overflow-y: auto;
  overscroll-behavior: contain;
}
.en-ventana .elegir,
.en-ventana .cierre {
  flex: none;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
}
.scroll {
  min-width: 0;
}
.en-ventana .scroll {
  flex: 1 1 0;
  min-height: 0;
  overflow-y: auto;
  overscroll-behavior: contain;
  scrollbar-width: thin;
  scrollbar-color: var(--line-2) transparent;
  padding-right: 2px;
}
.cab h3 {
  margin: 0;
  font: 600 var(--t-xs) var(--font-mono);
  letter-spacing: 0.12em;
  text-transform: uppercase;
  color: var(--text-3);
}
.estado {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font: 500 var(--t-sm) var(--font-ui);
  color: var(--text-2);
}
.estado .punto {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--st-idle);
}
.estado.e-escuchando .punto {
  background: var(--miel);
  box-shadow: 0 0 0 3px var(--miel-soft);
  animation: latido 1.8s ease-in-out infinite;
}
.estado.e-sin_subtitulos .punto,
.estado.e-sin_pc .punto,
.estado.e-llena .punto {
  background: var(--st-blocked);
}
.estado.e-guardada .punto {
  background: var(--st-done);
}
.estado.e-terminando .punto {
  background: var(--st-working);
}
.cuenta {
  font: 500 var(--t-xs) var(--font-mono);
  font-variant-numeric: tabular-nums;
  color: var(--text-3);
}
@keyframes latido {
  50% {
    opacity: 0.45;
  }
}
.elegir,
.cierre,
.tope {
  display: grid;
  gap: 10px;
  padding: 0 6px;
}
.rotulo {
  margin: 0;
  font: 600 var(--t-2xs) var(--font-mono);
  letter-spacing: 0.09em;
  text-transform: uppercase;
  color: var(--text-3);
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.chip {
  position: relative;
  height: 28px;
  padding: 0 12px;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text-2);
  font-size: var(--t-sm);
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    border-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out;
}
.chip::before {
  content: '';
  position: absolute;
  inset: -8px -3px;
}
.chip.on {
  background: var(--accent-soft);
  border-color: var(--accent-line);
  color: var(--text);
}
.tema-campo {
  min-width: 0;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: var(--t-md);
  transition: border-color 120ms ease-out;
}
.tema-campo::placeholder {
  color: var(--text-3);
}
.tema-campo:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.ayuda,
.nota {
  margin: 0;
  padding: 0 6px;
  font-size: var(--t-sm);
  line-height: 1.45;
  color: var(--text-3);
  text-wrap: pretty;
}
.elegir .ayuda {
  padding: 0;
}
.aviso {
  margin: 0;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  background: var(--st-idle-soft);
  color: var(--text-2);
  font-size: var(--t-sm);
  line-height: 1.45;
  text-wrap: pretty;
}
.aviso-alerta {
  background: var(--st-blocked-soft);
  color: var(--text);
}
.extras > .aviso {
  margin-inline: 6px;
}
.en-ventana .extras > .aviso,
.en-ventana .extras > .nota,
.en-ventana .mostrar,
.en-ventana .tope {
  margin-inline: 0;
  padding-inline: 0;
}
.en-ventana .extras > .aviso {
  padding: 9px 12px;
  border-radius: var(--r-md);
}
.primario,
.suave,
.terminar {
  position: relative;
  height: 32px;
  padding: 0 16px;
  border: 0;
  border-radius: var(--r-pill);
  font-size: var(--t-md);
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out,
    opacity 120ms ease-out;
}
.primario::before,
.suave::before,
.terminar::before {
  content: '';
  position: absolute;
  inset: -6px -2px;
}
.primario {
  justify-self: start;
  background: var(--accent);
  color: var(--accent-ink);
}
.suave {
  justify-self: start;
  background: color-mix(in srgb, var(--text) 9%, transparent);
  color: var(--text);
}
.mostrar {
  display: grid;
  gap: 6px;
  padding: 0 6px;
}
.mostrar-fila {
  display: flex;
  gap: 8px;
  align-items: center;
}
.mostrar-campo {
  flex: 1;
  min-width: 0;
  height: 32px;
  padding: 0 12px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  background: transparent;
  color: var(--text);
  font: inherit;
  font-size: var(--t-md);
  transition: border-color 120ms ease-out;
}
.mostrar-campo::placeholder {
  color: var(--text-3);
}
.mostrar-campo:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.mostrar-boton {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding-left: 12px;
}
.mostrar-boton .ojo {
  flex: none;
}
.mostrar .nota {
  padding: 0 4px;
}
.mostrar .mirando {
  color: var(--text-2);
  animation: latido 1.6s ease-in-out infinite;
}
.terminar {
  background: transparent;
  color: var(--danger);
  box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--danger) 45%, transparent);
}
.terminar.principal {
  background: var(--danger);
  color: var(--bg-2);
  box-shadow: none;
}
button:disabled {
  opacity: 0.45;
  cursor: default;
}
button:active:not(:disabled) {
  scale: 0.96;
}
@media (hover: hover) and (pointer: fine) {
  .acc-grupo {
    opacity: 0;
  }
  .linea:hover .acc-grupo,
  .linea:focus-within .acc-grupo {
    opacity: 1;
  }
  .acc:hover:not(:disabled) {
    background: color-mix(in srgb, var(--text) 10%, transparent);
    color: var(--text);
  }
  .chip:hover:not(.on) {
    background: color-mix(in srgb, var(--text) 7%, transparent);
    color: var(--text);
  }
  .suave:hover:not(:disabled) {
    background: color-mix(in srgb, var(--text) 14%, transparent);
  }
  .terminar:hover:not(:disabled):not(.principal) {
    background: var(--danger-soft);
  }
  .texto:hover:not(:disabled) {
    background: color-mix(in srgb, var(--text) 6%, transparent);
  }
}
button:focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}
.acciones,
.controles {
  display: flex;
  gap: 8px;
  padding: 0 6px;
}
.controles {
  padding: 0;
  margin-left: auto;
}
.vacio {
  display: grid;
  justify-items: center;
  align-content: center;
  gap: 6px;
  margin: 6px 0;
  padding: 28px 20px;
  border: 1px dashed var(--line-2);
  border-radius: var(--r-lg);
  background: linear-gradient(180deg, color-mix(in srgb, var(--miel) 5%, transparent), transparent 70%);
  text-align: center;
}
.en-ventana .vacio {
  flex: 1;
  margin: 0;
}
.vacio-titulo {
  margin: 4px 0 0;
  font: 600 var(--t-md) var(--font-ui);
  color: var(--text);
}
.vacio-texto {
  margin: 0;
  max-width: 28ch;
  font-size: var(--t-sm);
  line-height: 1.45;
  color: var(--text-3);
  text-wrap: balance;
}
.onda {
  position: relative;
  display: grid;
  place-items: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--miel-soft);
  color: var(--miel);
}
.onda i {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 1px solid color-mix(in srgb, var(--miel) 50%, transparent);
  opacity: 0;
  animation: onda 2.8s var(--ease-out) infinite;
}
.onda i:nth-child(2) {
  animation-delay: 0.9s;
}
.onda i:nth-child(3) {
  animation-delay: 1.8s;
}
.onda.quieta {
  background: var(--st-idle-soft);
  color: var(--text-3);
}
.onda.quieta i {
  animation: none;
}
@keyframes onda {
  0% {
    opacity: 0.7;
    scale: 1;
  }
  100% {
    opacity: 0;
    scale: 1.9;
  }
}
.lista {
  position: relative;
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 2px;
}
.linea {
  position: relative;
  display: grid;
  gap: 4px;
  padding-bottom: 4px;
  border-radius: var(--r-md);
}
.en-ventana .lista {
  gap: 8px;
}
.en-ventana .linea {
  padding: 4px 4px 8px;
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--surface);
  transition:
    background-color 120ms ease-out,
    border-color 120ms ease-out;
}
.en-ventana .linea.hay {
  border-color: var(--line-2);
}
.en-ventana .acc {
  width: 36px;
  height: 36px;
}
@media (hover: hover) and (pointer: fine) {
  .en-ventana .linea:hover {
    background: var(--surface-2);
    border-color: var(--line-2);
  }
}
.linea.con-acc .texto {
  padding-right: 80px;
}
.acc-grupo {
  position: absolute;
  top: 2px;
  right: 4px;
  display: flex;
  gap: 2px;
  transition: opacity 120ms ease-out;
}
.acc {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  padding: 0;
  border: 0;
  border-radius: var(--r-sm);
  background: transparent;
  color: var(--text-3);
  cursor: pointer;
  transition:
    background-color 120ms ease-out,
    color 120ms ease-out,
    scale 150ms ease-out;
}
.sello {
  justify-self: start;
  margin: 0 8px;
  padding: 1px 8px;
  border-radius: var(--r-pill);
  background: color-mix(in srgb, var(--miel) 18%, transparent);
  color: var(--text-2);
  font: 600 var(--t-2xs) var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
}
.fila-nota {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 8px;
  margin: 0 8px;
}
.fila-nota .sello {
  margin: 0;
}
.acc.mem {
  position: relative;
  display: inline-flex;
  align-items: center;
  width: auto;
  height: auto;
  min-height: 28px;
  padding: 0 10px;
  border: 1px solid var(--line-2);
  border-radius: var(--r-pill);
  font-size: var(--t-xs);
  touch-action: manipulation;
}
.acc.mem::before {
  content: '';
  position: absolute;
  inset: -8px -4px;
}
.en-memoria {
  color: var(--text-3);
  font-size: var(--t-xs);
}
.texto {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px;
  align-items: baseline;
  width: 100%;
  min-height: 36px;
  padding: 7px 8px;
  border: 0;
  border-radius: var(--r-md);
  background: transparent;
  color: var(--text);
  text-align: left;
  font-size: var(--t-md);
  line-height: 1.4;
  cursor: pointer;
  transition: background-color 120ms ease-out;
}
.texto:disabled {
  opacity: 1;
  cursor: default;
}
.tipo {
  font: 600 var(--t-2xs) var(--font-mono);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--text-3);
}
.tipo.t-pregunta {
  color: var(--st-working);
}
.tipo.t-requerimiento {
  color: var(--miel);
}
.tipo.t-clave {
  color: var(--st-fondo);
}
.cuerpo {
  min-width: 0;
  overflow-wrap: anywhere;
  text-wrap: pretty;
}
.resp {
  margin: 0 8px 0 8px;
  padding: 8px 10px;
  border-radius: var(--r-md);
  background: color-mix(in srgb, var(--text) 5%, transparent);
  font-size: var(--t-sm);
  line-height: 1.5;
  color: var(--text-2);
}
.resp-texto {
  margin: 0;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  text-wrap: pretty;
  color: var(--text);
}
.resp.espera {
  color: var(--text-3);
  animation: latido 1.6s ease-in-out infinite;
}
.resp.mal {
  background: var(--danger-soft);
  color: var(--text);
}
.archivos {
  list-style: none;
  margin: 8px 0 0;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.archivo {
  max-width: 100%;
  padding: 2px 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  border-radius: var(--r-xs);
  background: color-mix(in srgb, var(--text) 8%, transparent);
  color: var(--text-2);
  font: 500 var(--t-xs) var(--font-mono);
}
.error {
  margin: 0 6px;
  padding: 8px 10px;
  border-radius: var(--r-sm);
  background: var(--danger-soft);
  color: var(--text);
  font-size: var(--t-sm);
}
.lin-enter-active {
  transition:
    opacity 220ms var(--ease-out),
    transform 220ms var(--ease-out);
}
.lin-enter-from {
  opacity: 0;
  transform: translateY(-6px);
}
.lin-leave-active {
  position: absolute;
  left: 0;
  right: 0;
  transition:
    opacity 160ms var(--ease-out),
    transform 160ms var(--ease-out);
}
.lin-leave-to {
  opacity: 0;
  transform: translateX(16px);
}
.lin-move {
  transition: transform 200ms var(--ease-out);
}
@media (prefers-reduced-motion: reduce) {
  .lin-enter-active,
  .lin-leave-active,
  .lin-move,
  .acc-grupo,
  .acc,
  .chip,
  .primario,
  .suave,
  .terminar {
    transition: none;
  }
  .mostrar-campo {
    transition: none;
  }
  .onda i,
  .en-ventana .linea,
  .estado.e-escuchando .punto,
  .resp.espera,
  .mostrar .mirando {
    animation: none;
  }
}
</style>

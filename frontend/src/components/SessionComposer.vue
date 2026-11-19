<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { sessionDraft } from '../lib/drafts'
import { useDraft } from '../state/draft'
import { composerKeys, enterSends, replyProblem, textoProblem } from '../lib/reply'
import { stopErr, stopOk, stopSession, stopping } from '../state/app'
import { sendFromSession, type PendingFile } from '../state/session'
import { useAttachments } from '../state/attachments'
import { useFileIntake } from '../state/pegar'
import { useVozInput } from '../state/voz'
import { finePointer, haptic } from '../motion'
import { autosizeArea } from '../lib/autosize'
import AttachButton from './AttachButton.vue'
import AttachChips from './AttachChips.vue'
import VozButton from './VozButton.vue'
import VozStrip from './VozStrip.vue'
import EnterKey from './EnterKey.vue'
import Icon from './Icon.vue'

const props = defineProps<{ paneId: string; label: string; name: string; blocked: boolean; working: boolean }>()

const text = ref('')
const ta = ref<HTMLTextAreaElement | null>(null)
const att = useAttachments()
const { voz, onKeydown: onVozKey } = useVozInput(ta, text, () => nextTick(autosize))
watch(() => props.paneId, () => voz.cancel())

const canSend = computed(() => !props.blocked && !voz.busy.value && !att.busy.value && !att.failed.value && !replyProblem(text.value, att.ids.value.length))
const keys = computed(() => composerKeys({ working: props.working, blocked: props.blocked, texto: text.value, files: att.items.value.length }))
const showStop = computed(() => keys.value.key === 'stop')
const intake = useFileIntake(att.add, () => props.blocked)
const problem = computed(() => (text.value.trim() ? textoProblem(text.value) : null))

function autosize() {
  const el = ta.value
  if (!el) return
  const line = parseFloat(getComputedStyle(el).lineHeight) || 21
  autosizeArea(el, line * 6 + 14)
}

const draft = useDraft(text, () => sessionDraft(props.paneId), () => nextTick(autosize))


const enter = ref<InstanceType<typeof EnterKey> | null>(null)

async function submit() {
  if (!canSend.value) return
  const value = text.value
  const files: PendingFile[] = att.items.value
    .filter((a) => a.status === 'ready' && a.id)
    .map((a) => ({ id: a.id!, name: a.name, kind: a.kind, preview: a.preview }))
  const previews = att.items.value.map((a) => a.preview).filter((u): u is string => !!u)
  enter.value?.fire()
  text.value = ''
  draft.clear()
  att.items.value = []
  nextTick(autosize)
  sendFromSession(props.paneId, props.label, value, files)
  previews.forEach((u) => setTimeout(() => URL.revokeObjectURL(u), 120_000))
}

async function stop() {
  if (stopping[props.paneId]) return
  haptic(10)
  if (await stopSession(props.paneId)) haptic([12, 40, 20])
}

function onKey(e: KeyboardEvent) {
  if (!enterSends(e, finePointer(), keys.value.queues)) return
  e.preventDefault()
  void submit()
}
</script>

<template>
  <div
    class="composer"
    :class="{ blocked }"
    @click.stop
    @keydown="onVozKey"
    @dragenter="intake.onDragEnter"
    @dragover="intake.onDragOver"
    @dragleave="intake.onDragLeave"
    @drop="intake.onDrop"
  >
    <VozStrip v-if="voz.available.value" :voz="voz" />
    <form class="field" @submit.prevent="submit">
      <AttachChips :items="att.items.value" :notice="att.notice.value" @remove="att.remove" @retry="att.retry" />
      <AttachButton :disabled="blocked" :count="att.items.value.length" @pick="att.add" />
      <textarea
        ref="ta"
        v-model="text"
        rows="1"
        :disabled="blocked"
        :placeholder="blocked ? 'Esperando aprobación…' : keys.queues ? 'Enter para encolar…' : 'Escribí a esta sesión…'"
        :aria-label="`Escribir a ${name}`"
        enterkeyhint="send"
        @input="autosize"
        @blur="draft.flush"
        @keydown="onKey"
        @paste="intake.onPaste"
      />
      <EnterKey
        ref="enter"
        :mode="showStop ? 'stop' : 'send'"
        :tone="showStop ? 'danger' : 'accent'"
        :disabled="showStop ? !!stopping[paneId] : !canSend"
        :busy="showStop ? !!stopping[paneId] : att.busy.value"
        :label="att.busy.value ? 'Subiendo archivos' : 'Enviar'"
        stop-label="Frenar la sesión"
        :title="showStop ? 'Frenar (como Esc en la terminal) · si escribís, vuelve a ser Enter' : undefined"
        @stop="stop"
      >
        <VozButton v-if="voz.available.value" :voz="voz" :disabled="blocked" fill />
      </EnterKey>
      <Transition name="drop">
        <div v-if="intake.dragging.value" class="drop" aria-hidden="true"><Icon name="clip" :size="16" /> Soltá para adjuntar</div>
      </Transition>
    </form>
    <p v-if="problem" class="note" role="alert"><Icon name="warn" :size="12" /> {{ problem }}</p>
    <p v-if="stopErr[paneId]" class="note" role="alert"><Icon name="warn" :size="12" /> {{ stopErr[paneId] }}</p>
    <p v-if="stopOk[paneId]" class="help" role="status">Frenada</p>
  </div>
</template>

<style scoped>
.composer {
  display: grid;
  gap: 4px;
}
.field {
  position: relative;
}
.drop {
  position: absolute;
  inset: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  border-radius: inherit;
  pointer-events: none;
  color: var(--accent);
  font-size: var(--t-lg);
  font-weight: 600;
  background: color-mix(in srgb, var(--surface) 82%, transparent);
  box-shadow: inset 0 0 0 2px var(--accent-line);
  outline: 1.5px dashed var(--accent);
  outline-offset: -7px;
  backdrop-filter: blur(2px);
}
.drop-enter-active, .drop-leave-active { transition: opacity 0.18s; }
.drop-enter-from, .drop-leave-to { opacity: 0; }
.field {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr) auto;
  align-items: stretch;
  gap: 4px;
  padding: 5px 5px 2px 5px;
  border-radius: 16px;
  background: var(--surface);
  border: 1px solid var(--line-2);
  transition: border-color 0.25s, box-shadow 0.35s var(--ease-out), opacity 0.2s;
}
.field:focus-within {
  border-color: var(--accent-line);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
.field :deep(.clip) {
  margin-bottom: 3px;
}
.blocked .field {
  opacity: 0.55;
}
textarea {
  flex: 1;
  min-width: 0;
  resize: none;
  border: 0;
  outline: none !important;
  background: none;
  color: var(--text);
  font: inherit;
  font-size: 15px;
  line-height: 1.5;
  padding: 7px 4px;
  min-height: 72px;
}
@media (min-width: 1024px) {
  textarea { min-height: 62px; }
}
textarea::placeholder {
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
textarea:disabled {
  cursor: not-allowed;
}
.help {
  margin: 0 6px;
  font-size: 12px;
  color: var(--text-3);
}
.note {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 4px;
  font-size: 12px;
  color: var(--danger);
}
</style>

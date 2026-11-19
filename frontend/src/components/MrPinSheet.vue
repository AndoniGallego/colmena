<script setup lang="ts">
import { computed } from 'vue'
import { confirmarPin, mrSel, mrs, mrsPin } from '../state/mrs'
import TerminalPinSheet from './TerminalPinSheet.vue'

const mr = computed(() => mrs.detalle ?? mrSel.value)
const nombre = computed(() => (mr.value ? `!${mr.value.iid} de ${mr.value.repo_corto}` : 'el MR'))
const merge = computed(() => mrsPin.accion === 'mergear')
const note = computed(() =>
  merge.value
    ? `Se mergea ${nombre.value} en ${mr.value?.target || 'su rama destino'}, tal como está ahora en GitLab. No se puede deshacer desde acá.`
    : `Se cierra ${nombre.value} sin mergear. Se puede reabrir desde GitLab.`,
)
</script>

<template>
  <TerminalPinSheet
    :open="mrsPin.open"
    :busy="mrsPin.busy"
    :error="mrsPin.error"
    :listo="mrsPin.listo"
    :listo-txt="mrsPin.listoTxt"
    :locked-until="mrsPin.lockedUntil"
    :title="merge ? 'Mergear con tu PIN' : 'Cerrar con tu PIN'"
    :note="note"
    :cta="merge ? 'Mergear' : 'Cerrar el MR'"
    :danger="!merge"
    @submit="confirmarPin"
    @close="mrsPin.open = false"
  />
</template>

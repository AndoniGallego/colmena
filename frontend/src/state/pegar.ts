import { ref } from 'vue'
import { carriesFiles, filesFrom, hasText } from '../lib/pegar'

/** Ctrl+V y arrastrar archivos entran por el mismo add() que el clip, con sus mismas validaciones. */
export function useFileIntake(add: (files: File[]) => void, disabled: () => boolean) {
  const dragging = ref(false)
  let depth = 0

  function onPaste(e: ClipboardEvent) {
    if (disabled()) return
    const files = filesFrom(e.clipboardData)
    if (!files.length) return
    if (!hasText(e.clipboardData)) e.preventDefault()
    add(files)
  }

  function onDragEnter(e: DragEvent) {
    if (disabled() || !carriesFiles(e.dataTransfer)) return
    e.preventDefault()
    depth++
    dragging.value = true
  }

  function onDragOver(e: DragEvent) {
    if (disabled() || !carriesFiles(e.dataTransfer)) return
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }

  function onDragLeave() {
    if (!dragging.value) return
    depth = Math.max(0, depth - 1)
    if (!depth) dragging.value = false
  }

  function onDrop(e: DragEvent) {
    depth = 0
    dragging.value = false
    if (disabled() || !carriesFiles(e.dataTransfer)) return
    e.preventDefault()
    const files = filesFrom(e.dataTransfer)
    if (files.length) add(files)
  }

  return { dragging, onPaste, onDragEnter, onDragOver, onDragLeave, onDrop }
}

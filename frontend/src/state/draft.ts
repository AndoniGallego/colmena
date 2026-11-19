import { onBeforeUnmount, watch, type Ref } from 'vue'
import { getDraft, putDraft } from '../lib/drafts'
import { loadDrafts, saveDrafts } from '../lib/storage'

const DEBOUNCE_MS = 300

export function useDraft(text: Ref<string>, key: () => string, onRestore: () => void) {
  let timer: ReturnType<typeof setTimeout> | undefined

  function persist(k: string, value: string) {
    saveDrafts(putDraft(loadDrafts(), k, value))
  }
  function flush() {
    if (timer === undefined) return
    clearTimeout(timer)
    timer = undefined
    persist(key(), text.value)
  }
  function clear() {
    clearTimeout(timer)
    timer = undefined
    persist(key(), '')
  }
  function restore() {
    text.value = getDraft(loadDrafts(), key())
    onRestore()
  }

  if (!text.value) restore()

  watch(text, () => {
    clearTimeout(timer)
    timer = setTimeout(flush, DEBOUNCE_MS)
  })
  watch(key, (_, old) => {
    clearTimeout(timer)
    timer = undefined
    persist(old, text.value)
    restore()
  })

  const onHide = () => {
    if (document.visibilityState === 'hidden') flush()
  }
  window.addEventListener('pagehide', flush)
  document.addEventListener('visibilitychange', onHide)
  onBeforeUnmount(() => {
    window.removeEventListener('pagehide', flush)
    document.removeEventListener('visibilitychange', onHide)
    flush()
  })

  return { flush, clear }
}

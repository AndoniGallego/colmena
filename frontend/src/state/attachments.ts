import { computed, markRaw, onBeforeUnmount, ref } from 'vue'
import { ApiError } from '../api/types'
import { checkFile, kindOf, type AttachKind } from '../lib/attachments'
import { uploadFile } from './app'

export interface Attachment {
  key: string
  name: string
  size: number
  kind: AttachKind
  status: 'uploading' | 'ready' | 'error'
  progress: number
  id?: string
  preview?: string
  error?: string
  file: File
}

let seq = 0

/** Files are uploaded as soon as they are picked; sending waits until none is still in flight. */
export function useAttachments() {
  const items = ref<Attachment[]>([])
  const notice = ref<string | null>(null)
  const controllers = new Map<string, AbortController>()

  const find = (key: string) => items.value.find((a) => a.key === key)
  const release = (a: Attachment) => a.preview && URL.revokeObjectURL(a.preview)

  async function start(key: string) {
    const att = find(key)
    if (!att) return
    const controller = new AbortController()
    controllers.set(key, controller)
    att.status = 'uploading'
    att.progress = 0
    att.error = undefined
    try {
      const up = await uploadFile(att.file, (f) => (att.progress = f), controller.signal)
      att.id = up.id
      att.progress = 1
      att.status = 'ready'
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      att.status = 'error'
      att.error = e instanceof ApiError ? e.detail : 'No pude subir el archivo'
    } finally {
      controllers.delete(key)
    }
  }

  function add(files: FileList | File[] | null) {
    notice.value = null
    for (const file of Array.from(files ?? [])) {
      const problem = checkFile(file, items.value.length)
      if (problem) {
        notice.value = `${file.name}: ${problem}`
        continue
      }
      const kind = kindOf(file.name)!
      const key = `a${Date.now().toString(36)}${seq++}`
      items.value.push({
        key,
        name: file.name,
        size: file.size,
        kind,
        status: 'uploading',
        progress: 0,
        preview: kind === 'image' ? URL.createObjectURL(file) : undefined,
        file: markRaw(file),
      })
      void start(key)
    }
  }

  function remove(key: string) {
    controllers.get(key)?.abort()
    const i = items.value.findIndex((a) => a.key === key)
    if (i === -1) return
    release(items.value[i])
    items.value.splice(i, 1)
  }

  function clear() {
    items.value.forEach(release)
    items.value = []
    notice.value = null
  }

  onBeforeUnmount(() => {
    controllers.forEach((c) => c.abort())
    items.value.forEach(release)
  })

  return {
    items,
    notice,
    add,
    remove,
    clear,
    retry: (key: string) => start(key),
    busy: computed(() => items.value.some((a) => a.status === 'uploading')),
    failed: computed(() => items.value.some((a) => a.status === 'error')),
    ids: computed(() => items.value.flatMap((a) => (a.status === 'ready' && a.id ? [a.id] : []))),
  }
}

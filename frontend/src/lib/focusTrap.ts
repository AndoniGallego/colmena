import { nextTick, onBeforeUnmount, type Ref, watch } from 'vue'

export type FocusTrapOpts = {
  onEscape?: () => void
  initial?: () => HTMLElement | null | undefined
}

const FOCUSABLE =
  'button:not(:disabled), [href], input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [tabindex]:not([tabindex="-1"])'

type TrapEntry = {
  panel: Ref<HTMLElement | null>
  opts: FocusTrapOpts
}

const trapStack: TrapEntry[] = []
const handledKeydowns = new WeakSet<Event>()

function topTrap(): TrapEntry | undefined {
  return trapStack[trapStack.length - 1]
}

function ensureDocumentListener() {
  if (trapStack.length === 1) {
    document.addEventListener('keydown', onDocumentKeydown)
  }
}

function maybeRemoveDocumentListener() {
  if (trapStack.length === 0) {
    document.removeEventListener('keydown', onDocumentKeydown)
  }
}

function pushTrap(entry: TrapEntry) {
  if (trapStack.includes(entry)) return
  trapStack.push(entry)
  ensureDocumentListener()
}

function popTrap(entry: TrapEntry) {
  const i = trapStack.indexOf(entry)
  if (i === -1) return
  trapStack.splice(i, 1)
  maybeRemoveDocumentListener()
}

function onDocumentKeydown(e: KeyboardEvent) {
  if (handledKeydowns.has(e)) return
  const top = topTrap()
  if (!top) return
  const root = top.panel.value
  if (!root) return

  if (e.key === 'Escape') {
    if (top.opts.onEscape) {
      e.stopPropagation()
      top.opts.onEscape()
    }
    return
  }

  if (e.key !== 'Tab') return
  const active = document.activeElement as HTMLElement | null
  if (active && root.contains(active)) return
  e.preventDefault()
  const items = focusableIn(root)
  const el = items[0] ?? root
  if (el === root && !root.hasAttribute('tabindex')) root.tabIndex = -1
  el.focus()
}

export function visible(el: HTMLElement): boolean {
  if (el.hidden) return false
  if (el.closest('[hidden]')) return false
  if (getComputedStyle(el).display === 'none') return false
  return true
}

export function focusableIn(root: HTMLElement): HTMLElement[] {
  return [...root.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(visible)
}

export function useFocusTrap(
  panel: Ref<HTMLElement | null>,
  open: Ref<boolean> | (() => boolean),
  opts: FocusTrapOpts = {},
) {
  let opener: HTMLElement | null = null
  const entry: TrapEntry = { panel, opts }

  function isOpen(): boolean {
    return typeof open === 'function' ? open() : open.value
  }

  function focusInitial() {
    const root = panel.value
    if (!root) return
    if (root.querySelector('[autofocus]')) return
    if (root.contains(document.activeElement)) return
    const el = opts.initial?.() ?? focusableIn(root)[0] ?? root
    if (el === root && !root.hasAttribute('tabindex')) root.tabIndex = -1
    el.focus()
  }

  function restore() {
    popTrap(entry)
    if (opener && document.contains(opener)) opener.focus()
    opener = null
  }

  async function onOpen() {
    opener = document.activeElement as HTMLElement | null
    await nextTick()
    if (!isOpen() || !panel.value) return
    pushTrap(entry)
    focusInitial()
  }

  if (typeof open !== 'function') {
    watch(
      open,
      async (on) => {
        if (!on) {
          restore()
          return
        }
        await onOpen()
      },
      { flush: 'post' },
    )
  } else {
    watch(
      () => [panel.value, isOpen()] as const,
      async ([el, on], prev) => {
        const prevEl = prev?.[0]
        const prevOn = prev?.[1]
        const wasOpen = !!prevOn && !!prevEl
        const nowOpen = on && !!el
        if (nowOpen && !wasOpen) await onOpen()
        else if (wasOpen && !nowOpen) restore()
      },
      { flush: 'post' },
    )
  }

  onBeforeUnmount(restore)

  function onKeydown(e: KeyboardEvent) {
    if (entry !== topTrap()) return

    if (e.key === 'Escape') {
      if (opts.onEscape) {
        handledKeydowns.add(e)
        e.stopPropagation()
        opts.onEscape()
      }
      return
    }
    if (e.key !== 'Tab' || !panel.value) return
    const items = focusableIn(panel.value)
    if (!items.length) return
    const first = items[0]
    const last = items[items.length - 1]
    const active = document.activeElement as HTMLElement | null
    if (e.shiftKey && (active === first || active === panel.value)) {
      handledKeydowns.add(e)
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && active === last) {
      handledKeydowns.add(e)
      e.preventDefault()
      first.focus()
    }
  }

  return { onKeydown }
}

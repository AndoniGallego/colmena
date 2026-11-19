export interface AutofocoCtx {
  desktop: boolean
  punteroFino: boolean
  editando: boolean
}

export function debeAutofocoAlAbrir(c: AutofocoCtx): boolean {
  return c.desktop && c.punteroFino && !c.editando
}

export function estaEditando(el: Element | null): boolean {
  if (!el) return false
  if (el instanceof HTMLElement && el.isContentEditable) return true
  return el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !['button', 'checkbox', 'radio'].includes((el as HTMLInputElement).type))
}

import { copyText as copyTextDefault } from './clipboard'

export function textoACopiar(pre: HTMLElement): string {
  return pre.querySelector('code')?.textContent ?? ''
}

type CopiaOpts = {
  copyText?: (text: string) => Promise<boolean>
}

export function instalarCopiaCodigo(doc: Document = document, opts: CopiaOpts = {}): () => void {
  const copyText = opts.copyText ?? copyTextDefault

  const onClick = (e: Event) => {
    const t = e.target
    if (!t || typeof (t as Element).closest !== 'function') return
    const btn = (t as Element).closest('.md-copy')
    if (!btn) return
    const pre = btn.closest('pre.md-code')
    if (!pre) return

    e.stopPropagation()
    const text = textoACopiar(pre as HTMLElement)
    void (async () => {
      const ok = await copyText(text)
      if (!ok) {
        btn.classList.add('copia-fallo')
        btn.setAttribute('aria-label', 'No pude copiar')
        setTimeout(() => {
          btn.classList.remove('copia-fallo')
          btn.setAttribute('aria-label', 'Copiar código')
        }, 2200)
        return
      }
      btn.classList.add('copiado')
      btn.setAttribute('aria-label', 'Copiado')
      setTimeout(() => {
        btn.classList.remove('copiado')
        btn.setAttribute('aria-label', 'Copiar código')
      }, 1800)
    })()
  }

  doc.addEventListener('click', onClick)
  return () => doc.removeEventListener('click', onClick)
}

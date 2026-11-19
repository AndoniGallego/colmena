import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it } from 'vitest'
import AttachThumbs from './AttachThumbs.vue'

const render = (props: { ids: string[]; images?: number; solo?: boolean }) => renderToString(createSSRApp({ render: () => h(AttachThumbs, props) }))

describe('AttachThumbs', () => {
  it('imágenes como miniatura y el resto como archivo', async () => {
    const html = await render({ ids: ['20261102-101010-captura.png', '20261102-101011-notas.md'], solo: true })
    expect(html).toContain('class="files solo"')
    expect(html).toContain('<img src="/api/uploads/20261102-101010-captura.png"')
    expect(html).toContain('alt="captura.png"')
    expect(html).toMatch(/class="doc"[^>]*href="\/api\/uploads\/20261102-101011-notas\.md"|href="\/api\/uploads\/20261102-101011-notas\.md"[^>]*class="doc"/)
    expect(html).toContain('notas.md')
  })
})

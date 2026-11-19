import { beforeEach, describe, expect, it, vi } from 'vitest'
import { limpiarPedidoEnUrl, pedidoIdDesdeBusqueda } from './pedidosPestana'

describe('deep link ?pedido=', () => {
  beforeEach(() => {
    vi.stubGlobal('history', { replaceState: vi.fn(), state: null })
    vi.stubGlobal('location', {
      search: '?pedido=550e8400-e29b-41d4-a716-446655440000',
      pathname: '/',
    })
  })

  it('lee el id y limpia la URL', () => {
    const id = pedidoIdDesdeBusqueda(location.search)
    expect(id).toBe('550e8400-e29b-41d4-a716-446655440000')
    const url = limpiarPedidoEnUrl(location.pathname + location.search)
    expect(url).toBe('/')
    history.replaceState(null, '', url)
    expect(history.replaceState).toHaveBeenCalledWith(null, '', '/')
  })
})

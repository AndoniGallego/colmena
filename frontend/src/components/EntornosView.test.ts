import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.stubGlobal('window', {
  matchMedia: () => ({ matches: false, addEventListener() {}, removeEventListener() {} }),
  innerWidth: 800,
  addEventListener() {},
  removeEventListener() {},
  scrollTo() {},
  visualViewport: null,
})

vi.mock('../lib/viewport', () => ({ desktop: { value: false } }))
vi.mock('../lib/keyboard', () => ({
  useKeyboard: () => ({ open: { value: false }, height: { value: null }, top: { value: 0 } }),
}))
vi.mock('../motion', () => ({
  useGsap: () => ({ run: (fn: () => void) => fn() }),
  isSoft: () => true,
  animateViewEnter: vi.fn(),
  gsap: {},
}))

const { estado } = vi.hoisted(() => {
  const estado = {
    enPrograma: true,
    notebook: '',
    lista: [] as unknown[],
    error: '',
    cargando: false,
    abriendo: [] as string[],
    cerrando: [] as string[],
    errores: {} as Record<string, string>,
    tuneles: {} as Record<string, unknown>,
  }
  return { estado }
})

vi.mock('../state/entornos', () => ({
  entornos: estado,
  closeEntornos: vi.fn(),
  cargarEntornos: vi.fn(),
  refrescarTuneles: vi.fn(),
  abrirEntorno: vi.fn(),
  abrirPuerto: vi.fn(),
  cerrarEntorno: vi.fn(),
  cambiarNotebook: vi.fn(),
}))

vi.mock('./Icon.vue', () => ({ default: { name: 'Icon', render: () => null } }))
vi.mock('./ViewFrame.vue', () => ({
  default: { name: 'ViewFrame', template: '<div><slot name="back" /><slot /></div>' },
}))
vi.mock('./InlineAlert.vue', () => ({
  default: { name: 'InlineAlert', template: '<p class="inline-alert"><slot /></p>' },
}))
vi.mock('./EntornosProbador.vue', () => ({
  default: { name: 'EntornosProbador', template: '<div class="en-probador-mock" />' },
}))

const { default: EntornosView } = await import('./EntornosView.vue')

const render = () => renderToString(createSSRApp({ render: () => h(EntornosView) }))

const vacioExtra = { salud: null, apagado: false, servicios: [] as { servicio: string; estado: 'corriendo'; codigo: null; hace_s: null }[] }

const tiendaA = {
  nombre: 'tienda-a',
  carpeta: '~/proyectos/acme/tienda-a',
  principal: 8088,
  puertos: [{ puerto: 8088, servicio: 'tienda-b', puerto_contenedor: 3000, abrible: true }],
  ...vacioExtra,
}
const ps9v = {
  nombre: 'ps9',
  carpeta: '~/proyectos/acme/ps9',
  principal: 8080,
  puertos: [
    { puerto: 8080, servicio: 'web', puerto_contenedor: 80, abrible: true },
    { puerto: 80, servicio: 'viejo', puerto_contenedor: 80, abrible: false },
  ],
  ...vacioExtra,
}

const base = () => ({
  enPrograma: true,
  notebook: 'usuario@192.168.1.50',
  lista: [ps9v, tiendaA],
  error: '',
  cargando: false,
  abriendo: [],
  cerrando: [],
  errores: {},
  tuneles: { ps9: { estado: 'abierto', puertos: [8080], error: null } },
})

describe('EntornosView', () => {
  it('sin notebook guardada pide configurarla y deja el enlace para hacerlo', async () => {
    Object.assign(estado, base(), { notebook: '', tuneles: {} })
    const html = await render()
    expect(html).toContain('Configurá la notebook')
    expect(html).toContain('cambiar')
    expect(html).not.toContain('<code></code>')
  })

  it('Conectar usa btn-primary', async () => {
    Object.assign(estado, base(), { tuneles: {} })
    const html = await render()
    expect(html).toMatch(/class="[^"]*btn btn-primary[^"]*"/)
    expect(html).toContain('Conectar')
  })

  it('desconectando deshabilita el botón', async () => {
    Object.assign(estado, base(), { cerrando: ['ps9'] })
    const html = await render()
    expect(html).toContain('Desconectando…')
  })

  it('en la app muestra la notebook, conectar/desconectar y enlaces en chips', async () => {
    Object.assign(estado, base())
    const html = await render()
    expect(html).toContain('usuario@192.168.1.50')
    expect(html).toContain('cambiar')
    expect(html).toContain('2 entornos · 1 abierto')
    expect(html.match(/Conectar/g)?.length).toBe(1)
    expect(html).toContain('Desconectar')
    expect(html).not.toContain('>Abrir<')
    expect(html).toContain('Abierto')
    expect(html).toContain('Cerrado')
    expect(html).toContain('aria-label="Abrir web en el navegador"')
    expect(html).not.toContain('Puertos (')
    expect(html).not.toContain('localhost:80<')
  })

  it('en el navegador queda en solo lectura', async () => {
    Object.assign(estado, base(), { enPrograma: false, notebook: '', tuneles: {} })
    const html = await render()
    expect(html).toContain('Para abrir entornos usá la app de Windows')
    expect(html).not.toContain('Conectar')
    expect(html).not.toContain('cambiar')
    expect(html).toContain('ps9')
    expect(html).toContain('web')
    expect(html).toContain(':8080')
  })

  it('muestra conectando y el error de puerto ocupado', async () => {
    Object.assign(estado, base(), { tuneles: {}, abriendo: ['ps9'], errores: { 'tienda-a': 'el puerto 8088 ya está en uso en esta PC' } })
    const html = await render()
    expect(html).toContain('Conectando…')
    expect(html).toContain('Falló')
    expect(html).toContain('el puerto 8088 ya está en uso en esta PC')
  })

  it('cada tarjeta expone data-fase acorde al túnel', async () => {
    Object.assign(estado, base(), { tuneles: {}, abriendo: ['ps9'], errores: { 'tienda-a': 'el puerto 8088 ya está en uso en esta PC' } })
    const html = await render()
    expect(html).toMatch(/data-fase="abriendo"/)
    expect(html).toMatch(/data-fase="error"/)
    Object.assign(estado, base())
    const html2 = await render()
    expect(html2).toMatch(/data-fase="abierto"/)
    expect(html2).toMatch(/data-fase="cerrado"/)
  })

  it('marca data-principal en el puerto principal', async () => {
    Object.assign(estado, base())
    const html = await render()
    expect(html).toContain('data-principal')
  })

  it('sin túnel los chips son span; con túnel son botón con aria-label', async () => {
    Object.assign(estado, base(), { tuneles: {} })
    let html = await render()
    expect(html).toContain('class="en-chip"')
    expect(html).not.toContain('aria-label="Abrir web en el navegador"')
    Object.assign(estado, base())
    html = await render()
    expect(html).toContain('class="en-chip on"')
    expect(html).toContain('aria-label="Abrir web en el navegador"')
  })

  it('con fase abierto solo muestra Desconectar', async () => {
    Object.assign(estado, base())
    const html = await render()
    const ps9 = html.split('</article>').find((s) => s.includes('>ps9<'))
    expect(ps9).toContain('Desconectar')
    expect(ps9).not.toContain('Conectar')
  })

  it('explica el error de ssh y deja el original en Ver detalle', async () => {
    Object.assign(estado, base(), {
      tuneles: { ps9: { estado: 'error', puertos: [8080], error: 'usuario@192.168.1.50: Permission denied (publickey).' } },
    })
    const html = await render()
    expect(html).toContain('No llego a la notebook. ¿Estás en la red de casa y la dirección es la correcta?')
    expect(html).toContain('Ver detalle')
    expect(html).toContain('Permission denied (publickey).')
  })

  it('sin original en el error no muestra Ver detalle', async () => {
    Object.assign(estado, base(), { errores: { 'tienda-a': 'el puerto 8088 ya está en uso en esta PC' }, tuneles: {} })
    const html = await render()
    expect(html).toContain('el puerto 8088 ya está en uso en esta PC')
    expect(html).not.toContain('Ver detalle')
  })

  it('cargando sin lista muestra esqueletos', async () => {
    Object.assign(estado, base(), { lista: [], cargando: true })
    const html = await render()
    expect(html).toContain('Buscando entornos…')
    expect(html.match(/class="en-skel"/g)?.length).toBe(3)
  })

  it('semáforo de salud con data-salud y aria-label', async () => {
    Object.assign(estado, base(), {
      lista: [{ ...ps9v, salud: 'verde' }, { ...tiendaA, salud: 'amarillo' }, { ...tiendaA, nombre: 'rojo-x', salud: 'rojo' }],
    })
    const html = await render()
    expect(html).toContain('class="en-salud"')
    expect(html).toContain('data-salud="verde"')
    expect(html).toContain('aria-label="Salud: todo bien"')
    expect(html).toContain('data-salud="amarillo"')
    expect(html).toContain('aria-label="Salud: con problemas"')
    expect(html).toContain('data-salud="rojo"')
    expect(html).toContain('aria-label="Salud: caído"')
  })

  it('un servicio terminado no aparece en problemas', async () => {
    Object.assign(estado, base(), {
      lista: [
        {
          ...ps9v,
          salud: 'verde',
          servicios: [
            { servicio: 'web', estado: 'corriendo', codigo: null, hace_s: null },
            { servicio: 'migrate', estado: 'terminado', codigo: 0, hace_s: 3600 },
          ],
        },
      ],
      tuneles: {},
    })
    const html = await render()
    expect(html).not.toContain('migrate · Terminó')
    expect(html).not.toContain('migrate ·')
  })

  it('lista servicios con problemas con el texto exacto', async () => {
    Object.assign(estado, base(), {
      lista: [
        {
          ...ps9v,
          servicios: [{ servicio: 'hs-api', estado: 'caido', codigo: 1, hace_s: 300 }],
        },
      ],
      tuneles: {},
    })
    const html = await render()
    expect(html).toContain('hs-api · Caído · hace 5 min · código 1')
  })

  it('apagados van al details y no en la grilla principal', async () => {
    Object.assign(estado, base(), {
      lista: [
        { ...ps9v, apagado: true, salud: 'rojo' },
        { ...tiendaA, apagado: false },
      ],
      tuneles: {},
    })
    const html = await render()
    expect(html).toContain('Apagados (1)')
    const main = html.split('Apagados (1)')[0] ?? ''
    expect(main).not.toContain('>ps9<')
    expect(html).toContain('>tienda-a<')
  })

  it('botón Probar solo en tarjetas activas con puerto abrible', async () => {
    Object.assign(estado, base(), {
      lista: [
        ps9v,
        { ...tiendaA, puertos: [{ puerto: 1, servicio: 'x', puerto_contenedor: null, abrible: false }] },
        { ...ps9v, nombre: 'apag', apagado: true },
      ],
      tuneles: {},
    })
    const html = await render()
    expect((html.match(/Probar/g) ?? []).length).toBe(1)
    const apagados = html.split('Apagados')[1] ?? ''
    expect(apagados).not.toContain('Probar')
    const sinAbrible = html.split('>tienda-a<')[1]?.split('</article>')[0] ?? ''
    expect(sinAbrible).not.toContain('Probar')
  })

  it('Docker caído y lista vacía', async () => {
    Object.assign(estado, base(), { lista: [], tuneles: {}, error: 'Docker no responde' })
    const html = await render()
    expect(html).toContain('Docker no responde')
    expect(html).not.toContain('No hay entornos corriendo en la notebook')
    Object.assign(estado, { error: '', cargando: false, lista: [] })
    expect(await render()).toContain('No hay entornos corriendo en la notebook')
  })
})

import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

const src = readFileSync(new URL('./SessionChatView.vue', import.meta.url).pathname, 'utf8')

describe('SessionChatView acciones de terminal', () => {
  it('muestra Abrir terminal y no Terminal ni Enfocar', () => {
    expect(src).toContain('Abrir terminal')
    expect(src).not.toMatch(/>\s*Terminal\s*</)
    expect(src).not.toContain('Enfocar')
  })

  it('Abrir en la PC solo cuando no es desktop y hay vivo', () => {
    expect(src).toContain('Abrir en la PC')
    expect(src).toMatch(/v-if="showVivo && !desktop"/)
  })

  it('abrir terminal pide PIN al abrir', () => {
    expect(src).toMatch(/abrirVivo\([^)]+\{\s*pedirPin:\s*true\s*\}/)
  })
})

describe('SessionChatView atender sesión', () => {
  it('interacción en .sess llama atenderSesion', () => {
    expect(src).toContain('atenderSesion')
    expect(src).toMatch(/class="sess"[\s\S]*@keydown="onAtender"/)
    expect(src).toContain('@wheel.passive="onAtender"')
    expect(src).toContain('@touchstart.passive="onAtender"')
  })
})

describe('SessionChatView Ir a PC', () => {
  it('tiene el botón Ir a PC solo para terminales de Colmena, deshabilitado mientras envía', () => {
    expect(src).toContain('aria-label="Ir a PC"')
    expect(src).toContain('v-if="showIrAPc"')
    expect(src).toContain('irAPcSesion')
    expect(src).toContain('irAPcEnviando')
  })

  it('el botón nuevo usa otro ícono que el viejo y explica que abre la notebook', () => {
    const bloque = src.slice(src.indexOf('v-if="showIrAPc"'))
    const boton = bloque.slice(0, bloque.indexOf('</button>'))
    expect(boton).toContain('title="Abre una terminal en la notebook"')
    expect(boton).toContain('<Icon name="terminal"')
    expect(boton).not.toContain('name="monitor"')
    expect(src).toMatch(/aria-label="Abrir en la PC"[\s\S]*?<Icon name="monitor"/)
  })

  it('el estado enviando es por sesión y el aviso de error usa el estilo de error', () => {
    expect(src).toContain('irAPcEnviando[openSessionId')
    expect(src).toContain('err: !avisoIrAPc.ok')
  })
})

describe('SessionChatView cambios', () => {
  it('tiene el botón Cambios con contador y muestra la vista en lugar del chat', () => {
    expect(src).toContain('CambiosView')
    expect(src).toContain('aria-label="Ver cambios de la sesión"')
    expect(src).toMatch(/<CambiosView[^>]*v-if="verCambios && openSessionId"/)
    expect(src).toMatch(/class="scroll"[^>]*v-show="!verCambios"|v-show="!verCambios"[^>]*class="scroll"/)
    expect(src).toContain('cargarCambios')
  })
})

describe('SessionChatView salto desde una nota', () => {
  it('usa el composable del salto y le pasa el nombre de la sesión a los mensajes', () => {
    expect(src).toContain('useSaltoMensaje(')
    expect(src).toContain(':session-nombre=')
  })
})

describe('SessionChatView pedidos de pestaña', () => {
  it('el chat abierto muestra los pedidos de su sesión justo después de DialogCard', () => {
    expect(src).toMatch(/<DialogCard[^>]*\/>\s*<PedidosPestanaChat v-if="openSessionId" :session-id="openSessionId" \/>/)
  })
})

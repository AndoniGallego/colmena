// @vitest-environment jsdom
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const h = vi.hoisted(() => ({
  acciones: {
    cargarRepos: vi.fn(async () => undefined),
    escuchar: vi.fn(async (_r: string[], _t: boolean) => undefined),
    tocar: vi.fn(async (_id: string) => undefined),
    descartar: vi.fn(async (_id: string) => undefined),
    anotar: vi.fn(async (_id: string) => undefined),
    preguntarUltimo: vi.fn(async () => undefined),
    pausar: vi.fn(async () => undefined),
    seguir: vi.fn(async () => undefined),
    terminar: vi.fn(async () => undefined),
    nuevaReunion: vi.fn(),
    mostrarAhora: vi.fn(async (_p: string) => undefined),
    cargarNudo: vi.fn(async () => undefined),
  },
  abrirColmena: vi.fn(),
  abrirBiblioteca: vi.fn(),
}))

vi.mock('../../state/reunion', async () => {
  const { ref } = await import('vue')
  const real = await vi.importActual<typeof import('../../state/reunion')>('../../state/reunion')
  return {
    ...h.acciones,
    inicial: real.inicial,
    reunion: ref(real.inicial()),
    repos: ref([
      { ruta: '/home/u/development/ps9', nombre: 'ps9' },
      { ruta: '/home/u/development/colmena', nombre: 'colmena' },
    ]),
    errorReunion: ref<string | null>(null),
    mirando: ref<string | null>(null),
    nudoPrendido: ref<boolean | null>(true),
    puedeMostrar: real.puedeMostrar,
  }
})
vi.mock('../../state/notch', () => ({ abrirColmena: h.abrirColmena, abrirBiblioteca: h.abrirBiblioteca }))
vi.mock('../../state/app', async () => {
  const { ref } = await import('vue')
  return { pcNudoActivo: ref(true) }
})

import { pcNudoActivo } from '../../state/app'
import { inicial, reunion, errorReunion, mirando, nudoPrendido, type EstadoReunionFront } from '../../state/reunion'
import NotchReunion from './NotchReunion.vue'

const poner = (extra: Partial<EstadoReunionFront>) => {
  reunion.value = { ...inicial(), reunion: 'r1', estado: 'escuchando', lector: 'escuchando', copiloto: 'listo', ...extra }
}
const linea = (id: string, extra: Record<string, unknown> = {}) => ({ id, texto: `texto ${id}`, tipo: 'pregunta' as const, ...extra })
const boton = (w: ReturnType<typeof mount>, texto: string) => w.findAll('button').find((b) => b.text() === texto)

beforeEach(() => {
  vi.clearAllMocks()
  reunion.value = inicial()
  errorReunion.value = null
  mirando.value = null
  nudoPrendido.value = true
  pcNudoActivo.value = true
})

describe('NotchReunion', () => {
  it('inactiva: selector con Todos marcado, ayuda y Escuchar', async () => {
    const w = mount(NotchReunion)
    await flushPromises()
    expect(h.acciones.cargarRepos).toHaveBeenCalled()
    expect(boton(w, 'Todos')?.attributes('aria-pressed')).toBe('true')
    expect(boton(w, 'ps9')?.attributes('aria-pressed')).toBe('false')
    expect(w.text()).toContain('Abrí Subtítulos en vivo (Win+Ctrl+L)')
    await boton(w, 'Escuchar')!.trigger('click')
    expect(h.acciones.escuchar).toHaveBeenCalledWith([], true)
  })

  it('elegir un repo desmarca Todos y se manda esa ruta', async () => {
    const w = mount(NotchReunion)
    await boton(w, 'ps9')!.trigger('click')
    expect(boton(w, 'Todos')?.attributes('aria-pressed')).toBe('false')
    expect(boton(w, 'ps9')?.attributes('aria-pressed')).toBe('true')
    await boton(w, 'Escuchar')!.trigger('click')
    expect(h.acciones.escuchar).toHaveBeenCalledWith(['/home/u/development/ps9'], false)
    await boton(w, 'ps9')!.trigger('click')
    expect(boton(w, 'Todos')?.attributes('aria-pressed')).toBe('true')
  })

  describe('descartar y anotar por línea', () => {
    const por = (w: ReturnType<typeof mount>, etiqueta: string) => w.findAll(`button[aria-label="${etiqueta}"]`)
    it('cada línea detectada lleva Descartar y Anotar, las de Mostrame no', () => {
      poner({ lineas: [linea('l3', { tipo: 'mostrar' }), linea('l2', { tipo: 'requerimiento' }), linea('l1')] })
      const w = mount(NotchReunion)
      expect(por(w, 'Descartar')).toHaveLength(2)
      expect(por(w, 'Anotar')).toHaveLength(2)
      expect(w.findAll('li.linea')[0].find('button.acc').exists()).toBe(false)
    })
    it('Descartar llama a descartar sin disparar tocar', async () => {
      poner({ lineas: [linea('l1')] })
      const w = mount(NotchReunion)
      await por(w, 'Descartar')[0].trigger('click')
      expect(h.acciones.descartar).toHaveBeenCalledWith('l1')
      expect(h.acciones.tocar).not.toHaveBeenCalled()
    })
    it('Anotar llama a anotar sin disparar tocar', async () => {
      poner({ lineas: [linea('l1')] })
      const w = mount(NotchReunion)
      await por(w, 'Anotar')[0].trigger('click')
      expect(h.acciones.anotar).toHaveBeenCalledWith('l1')
      expect(h.acciones.tocar).not.toHaveBeenCalled()
    })
    it('una línea anotada muestra el sello y no se puede anotar de nuevo', () => {
      poner({ lineas: [linea('l1', { nota: 'n_1' })] })
      const w = mount(NotchReunion)
      expect(w.find('.sello').text()).toBe('Anotada')
      expect(w.find('button[aria-label="Anotar"]').exists()).toBe(false)
      expect(por(w, 'Descartar')).toHaveLength(1)
    })
    it('una línea que el Copiloto está buscando no se puede descartar', () => {
      poner({ lineas: [linea('l1', { respuesta: { estado: 'buscando', texto: '', archivos: [] } })] })
      const w = mount(NotchReunion)
      expect(por(w, 'Descartar')[0].attributes('disabled')).toBeDefined()
    })
  })

  it('escuchando: lista las líneas y al tocar una muestra buscando… y llama a tocar', async () => {
    poner({ lineas: [linea('l2'), linea('l1')] })
    h.acciones.tocar.mockImplementationOnce(async (id: string) => {
      reunion.value = {
        ...reunion.value,
        lineas: reunion.value.lineas.map((l) => (l.id === id ? { ...l, respuesta: { estado: 'buscando' as const, texto: '', archivos: [] } } : l)),
      }
    })
    const w = mount(NotchReunion)
    expect(w.findAll('li.linea')).toHaveLength(2)
    await w.findAll('button.texto')[0].trigger('click')
    expect(h.acciones.tocar).toHaveBeenCalledWith('l2')
    expect(w.text()).toContain('buscando…')
  })

  it('una respuesta muestra el texto y los archivos como chips', () => {
    poner({ lineas: [linea('l1', { respuesta: { estado: 'lista', texto: 'Sí, en el módulo X', archivos: ['src/pagos/reembolso.py', 'README.md'] } })] })
    const w = mount(NotchReunion)
    expect(w.text()).toContain('Sí, en el módulo X')
    const chips = w.findAll('.archivo')
    expect(chips.map((c) => c.text())).toEqual(['pagos/reembolso.py', 'README.md'])
    expect(chips[0].attributes('title')).toBe('src/pagos/reembolso.py')
  })

  it('con tope avisa y ofrece Preguntar por lo último', async () => {
    poner({ tope: true, detecciones: 12, topeDetecciones: 12 })
    const w = mount(NotchReunion)
    expect(w.text()).toContain('Llegué al tope de detecciones de esta reunión')
    await boton(w, 'Preguntar por lo último')!.trigger('click')
    expect(h.acciones.preguntarUltimo).toHaveBeenCalled()
  })

  it('con el tope en 0 dice que es solo a mano y no habla de tope', () => {
    poner({ soloAMano: true })
    const w = mount(NotchReunion)
    expect(w.text()).toContain('preguntá a mano')
    expect(w.text()).not.toContain('Llegué al tope')
    expect(boton(w, 'Preguntar por lo último')).toBeTruthy()
  })

  it('sin tope no ofrece Preguntar por lo último', () => {
    poner({})
    expect(boton(mount(NotchReunion), 'Preguntar por lo último')).toBeUndefined()
  })

  it('lector sin_subtitulos: pide abrirlos', () => {
    poner({ lector: 'sin_subtitulos' })
    expect(mount(NotchReunion).text()).toContain('No encuentro los subtítulos: abrilos con Win+Ctrl+L')
  })

  it('sin_pc y llena muestran su texto', () => {
    poner({ estado: 'sin_pc' })
    expect(mount(NotchReunion).text()).toContain('Perdí la conexión con la PC')
  })

  it('llena: Terminar queda habilitado, destacado y cierra la reunión', async () => {
    poner({ estado: 'llena' })
    const w = mount(NotchReunion)
    expect(w.text()).toContain('largo máximo')
    const t = boton(w, 'Terminar')!
    expect(t.attributes('disabled')).toBeUndefined()
    expect(t.classes()).toContain('principal')
    await t.trigger('click')
    expect(h.acciones.terminar).toHaveBeenCalled()
  })

  it('guardada: Ver en la Biblioteca abre ese ítem y Empezar otra vuelve al selector', async () => {
    const id = '0123456789abcdef0123456789abcdef'
    poner({ estado: 'guardada', biblioteca: id })
    const w = mount(NotchReunion)
    expect(w.text()).toContain('Reunión guardada')
    await boton(w, 'Ver en la Biblioteca')!.trigger('click')
    expect(h.abrirBiblioteca).toHaveBeenCalledWith(id)
    expect(h.abrirColmena).not.toHaveBeenCalled()
    await boton(w, 'Empezar otra')!.trigger('click')
    expect(h.acciones.nuevaReunion).toHaveBeenCalled()
  })

  it('guardada sin id de Biblioteca abre Colmena en general', async () => {
    poner({ estado: 'guardada', biblioteca: null })
    await boton(mount(NotchReunion), 'Ver en la Biblioteca')!.trigger('click')
    expect(h.abrirColmena).toHaveBeenCalled()
    expect(h.abrirBiblioteca).not.toHaveBeenCalled()
  })

  it('Pausar, Seguir y Terminar llaman a las acciones', async () => {
    poner({})
    const w = mount(NotchReunion)
    await boton(w, 'Pausar')!.trigger('click')
    expect(h.acciones.pausar).toHaveBeenCalled()
    await boton(w, 'Terminar')!.trigger('click')
    expect(h.acciones.terminar).toHaveBeenCalled()
    poner({ estado: 'pausada' })
    await w.vm.$nextTick()
    await boton(w, 'Seguir')!.trigger('click')
    expect(h.acciones.seguir).toHaveBeenCalled()
  })

  describe('Mostrame', () => {
    it('al montar consulta el estado del nudo', () => {
      poner({})
      mount(NotchReunion)
      expect(h.acciones.cargarNudo).toHaveBeenCalled()
    })
    it('con el nudo apagado el botón está deshabilitado y dice por qué', () => {
      poner({})
      nudoPrendido.value = false
      const w = mount(NotchReunion)
      expect(boton(w, 'Mostrame')!.attributes('disabled')).toBeDefined()
      expect(w.text()).toContain('Prendé el nudo en la bandeja')
    })
    it('con el Copiloto ocupado, deshabilitado', () => {
      poner({ ocupado: true })
      const w = mount(NotchReunion)
      expect(boton(w, 'Mostrame')!.attributes('disabled')).toBeDefined()
      expect(w.text()).toContain('El Copiloto está ocupado')
    })
    it('el click refresca el nudo y llama a mostrarAhora con el texto del campo', async () => {
      poner({})
      const w = mount(NotchReunion)
      h.acciones.cargarNudo.mockClear()
      const campo = w.find('input[type="text"]')
      expect(campo.attributes('maxlength')).toBe('300')
      expect(campo.attributes('placeholder')).toBe('¿Qué querés que te muestre?')
      await campo.setValue('¿cómo exporto esto?')
      await boton(w, 'Mostrame')!.trigger('click')
      expect(h.acciones.cargarNudo).toHaveBeenCalled()
      expect(h.acciones.mostrarAhora).toHaveBeenCalledWith('¿cómo exporto esto?')
    })
    it('con mirando se ve "Mirando la ventana…" y el botón queda deshabilitado', () => {
      poner({})
      mirando.value = 'capturando'
      const w = mount(NotchReunion)
      expect(w.find('[role="status"].mirando').text()).toContain('Mirando la ventana…')
      expect(boton(w, 'Mostrame')!.attributes('disabled')).toBeDefined()
    })
    it('una línea mostrar lleva la etiqueta Mostrame y no es tocable', () => {
      poner({ lineas: [linea('l1', { tipo: 'mostrar' })] })
      const w = mount(NotchReunion)
      const t = w.find('button.texto')
      expect(t.find('.tipo').text()).toBe('Mostrame')
      expect(t.attributes('disabled')).toBeDefined()
    })
    it('sin pcNudo no hay botón', () => {
      pcNudoActivo.value = false
      poner({})
      expect(boton(mount(NotchReunion), 'Mostrame')).toBeUndefined()
    })
  })

  it('un error de la acción se muestra como alerta', async () => {
    errorReunion.value = 'Ya hay una reunión en curso.'
    const w = mount(NotchReunion)
    expect(w.find('[role="alert"]').text()).toBe('Ya hay una reunión en curso.')
  })

  describe('layout de la ventana', () => {
    it('los controles viven en el encabezado, antes de la lista', () => {
      poner({ lineas: [linea('a')] })
      const w = mount(NotchReunion, { props: { ventana: true } })
      expect(w.classes()).toContain('en-ventana')
      const cab = w.find('header.cab')
      expect(cab.find('.controles').exists()).toBe(true)
      expect(cab.text()).toContain('Pausar')
      expect(cab.text()).toContain('Terminar')
      expect(w.findAll('.controles')).toHaveLength(1)
      const html = w.html()
      expect(html.indexOf('class="controles"')).toBeLessThan(html.indexOf('class="scroll"'))
    })

    it('la lista de líneas es el único contenedor de scroll', () => {
      poner({ lineas: [linea('a'), linea('b')] })
      const w = mount(NotchReunion, { props: { ventana: true } })
      const sc = w.find('.scroll')
      expect(sc.exists()).toBe(true)
      expect(sc.findAll('li.linea')).toHaveLength(2)
      expect(sc.find('.controles').exists()).toBe(false)
    })

    it('sin líneas muestra un estado vacío cuidado, no solo texto suelto', () => {
      poner({})
      const w = mount(NotchReunion, { props: { ventana: true } })
      expect(w.find('.scroll').exists()).toBe(false)
      expect(w.find('.vacio .onda').exists()).toBe(true)
      expect(w.find('.vacio').text()).toContain('Las preguntas que detecte aparecen acá.')
    })

    it('sin la prop (notch) no fija el alto', () => {
      poner({})
      expect(mount(NotchReunion).classes()).not.toContain('en-ventana')
    })
  })
})

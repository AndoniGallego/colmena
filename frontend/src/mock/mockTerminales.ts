import { ApiError, type Board, type ComandoBody, type VentanaAbierta, type RepetirPrep, type Terminal, type TerminalAuditoria, type TerminalConfig, type TerminalEstado, type TerminalPreview, type TerminalSalida } from '../api/types'

const E = '\x1b'
const T0 = Date.now()
const sgr = (code: string, text: string) => `${E}[${code}m${text}${E}[0m`

const term = (pane: string, titulo: string, cwd: string, proceso: string, estado: TerminalEstado, protegida = false): Terminal => ({
  pane_id: pane,
  terminal_id: `t-${pane}`,
  titulo,
  cwd,
  proceso,
  estado,
  protegida,
})

const LARGO = 'usuario@usuario-notebook: ~/proyectos/acme/ps9/app_prestashop/store/modules'

const PLAN: Record<string, Terminal[]> = {
  'w1:t2': [term('w1:pT1', LARGO, '~/proyectos/acme', 'bash', 'prompt')],
  'w1:t3': [term('w1:pT3', 'claude', '~/Proyectos/orquestador', 'claude', 'corriendo')],
  'wA:t1': [term('wA:pT1', 'npm run dev', '~/Proyectos/orquestador/frontend', 'node', 'corriendo'), term('wA:pT2', 'bash', '~/Proyectos/acmekit', 'bash', 'prompt')],
  'wP:t1': [term('wP:pT1', 'tail -f deploy.log', '~/proyectos/acme/ps9/var/log', 'tail', 'corriendo')],
  'w8:t2': [term('w8:pT1', 'bash', '~/proyectos/acme/ps9', 'bash', 'prompt')],
  'w5:tH': [term('w5:pH1', 'docker compose logs', '~/proyectos/acme/tienda-a', 'docker', 'corriendo'), term('w5:pH2', 'psql', '~/proyectos/acme/tienda-a', 'psql', 'corriendo')],
  'wS:t2': [term('wS:pT1', 'salida hostil de prueba', '~/Proyectos/orquestador', 'cat', 'corriendo')],
  'w9:t2': [term('w9:pT1', 'bash', '~/Proyectos/gastos-casa', 'bash', 'prompt')],
}

export function attachTerminales(board: Board) {
  for (const w of board.workspaces) for (const t of w.tabs) t.terminales = structuredClone(PLAN[t.id] ?? [])
}

export const PIN_ESCRITURA_MOCK = true

function vite(): string {
  const n = Math.floor((Date.now() - T0) / 2000)
  const out = [
    '',
    `  ${sgr('1;32', 'VITE')} ${sgr('32', 'v6.0.3')}  ${sgr('2', 'ready in')} ${sgr('1', '412')} ms`,
    '',
    `  ${sgr('32', '➜')}  ${sgr('1', 'Local')}:   ${sgr('36', 'http://localhost:5173/')}`,
    `  ${sgr('32', '➜')}  ${sgr('1', 'Network')}: ${sgr('2', 'use --host to expose')}`,
    '',
  ]
  for (let i = 0; i < 12 + n; i++) {
    const hh = String(10 + Math.floor(i / 60)).padStart(2, '0')
    const mm = String(i % 60).padStart(2, '0')
    const file = ['/src/App.vue', '/src/components/TerminalViewer.vue', '/src/state/terminales.ts', '/src/lib/ansi.ts'][i % 4]
    out.push(`${sgr('2', `${hh}:${mm}:07`)} ${sgr('36;1', '[vite]')} ${sgr('32', 'hmr update')} ${sgr('2', file)}${i % 7 === 3 ? ' ' + sgr('33', '(x2)') : ''}`)
  }
  if (n % 5 === 4) out.push(`${sgr('31;1', 'error')} ${sgr('31', 'Failed to resolve import "./nope"')}`)
  return out.join('\r\n') + '\r\n'
}

function tail(): string {
  const n = Math.floor((Date.now() - T0) / 1000)
  const out: string[] = []
  for (let i = 0; i < 24; i++) {
    const r = 40 + ((i * 53) % 200)
    const g = 120 + ((i * 29) % 120)
    const b = 200 - ((i * 37) % 150)
    out.push(`${E}[38;2;${r};${g};${b}m${'█'.repeat(8 + (i % 5))}${E}[0m ${sgr('2', `chunk ${i}`)} ${E}[48;5;${17 + i * 3}m  ${E}[0m`)
  }
  const pct = Math.min(100, (n * 7) % 140)
  let bar = ''
  for (let p = 0; p <= pct; p += 10) bar += `Descargando [${'#'.repeat(p / 10)}${' '.repeat(10 - p / 10)}] ${p}%\r`
  out.push(`${bar}`)
  return out.join('\r\n') + '\r\n'
}

const bash = (cwd: string) => `${sgr('1;32', 'cc@notebook')}:${sgr('1;34', cwd)}$ git status\r\nOn branch main\r\nnothing to commit, working tree clean\r\n${sgr('1;32', 'cc@notebook')}:${sgr('1;34', cwd)}$ `

function hostile(): string {
  return [
    '<script>window.__pwn = 1; alert("xss")</script>',
    '<img src=x onerror="window.__pwn = 2">',
    `${E}]8;;javascript:alert(1)${'\x07'}enlace OSC 8 (no debe ser clicable)${E}]8;;${'\x07'}`,
    `${E}]52;c;SGVsbG8gcG9ydGFwYXBlbGVz${'\x07'}texto tras OSC 52`,
    `${E}[2J${E}[H${E}[?1049h pantalla alternativa descartada`,
    'bidi: abc‮def‬ ghi ⁦x⁩',
    'ancho cero: a​b‍c﻿d',
    '\u009B31mC1 CSI no es color',
    `${E}[38;5;196mrojo 256${E}[0m ${E}[1;4;9;38;2;255;0;200mnegrita subrayado tachado${E}[0m ${E}[7minvertido${E}[0m`,
    'tabs:\tuno\tdos\tdos',
    ...Array.from({ length: 480 }, (_, i) => `línea ${String(i).padStart(3, '0')} ${'x'.repeat(i % 90)}`),
  ].join('\r\n') + '\r\n'
}

const BODY: Record<string, () => string> = {
  'wA:pT1': vite,
  'wA:pT2': () => bash('~/Proyectos/acmekit'),
  'wP:pT1': tail,
  'w8:pT1': () => bash('~/proyectos/acme/ps9'),
  'w5:pH1': () => Array.from({ length: 30 }, (_, i) => `${sgr('36', 'tienda-a-web-1')}  | GET /health 200 ${i}ms`).join('\r\n') + '\r\n',
  'w5:pH2': () => `psql (16.2)\r\ntienda_b=# `,
  'wS:pT1': hostile,
  'w9:pT1': () => bash('~/Proyectos/gastos-casa'),
  'w1:pT1': () => bash('~/proyectos/acme') + Array.from({ length: 6 }, (_, i) => `${'ancho '.repeat(40)}${i}`).join('\r\n') + '\r\n',
}

function digest(text: string): string {
  let h = 5381
  for (let i = 0; i < text.length; i++) h = ((h << 5) + h + text.charCodeAt(i)) | 0
  return (h >>> 0).toString(16).padStart(8, '0')
}

function escritura(t: Terminal): Pick<TerminalSalida, 'puede_escribir' | 'motivo'> {
  const off = new URLSearchParams(location.search).get('escritura') === '0'
  const motivo = off ? 'apagada' : t.estado === 'corriendo' ? 'ocupada' : t.estado === 'desconocido' ? 'desconocido' : null
  return { puede_escribir: motivo === null, motivo }
}

export async function mockSalida(paneId: string, rev: string, signal: AbortSignal): Promise<TerminalSalida> {
  await new Promise<void>((res, rej) => {
    const t = setTimeout(res, 160)
    signal.addEventListener('abort', () => {
      clearTimeout(t)
      rej(new DOMException('aborted', 'AbortError'))
    })
  })
  if (paneId.startsWith('mock:')) throw new ApiError(404, 'la terminal ya no está')
  const body = BODY[paneId]
  if (!body) throw new ApiError(404, 'la terminal ya no está')
  const t = Object.values(PLAN).flat().find((x) => x.pane_id === paneId)!
  const ansi = body()
  const revision = digest(ansi)
  const base = { revision, cwd: t.cwd, proceso: t.proceso, estado: t.estado, ...escritura(t) }
  if (rev === revision) return { sin_cambios: true, ansi: '', truncado: false, ...base }
  return { sin_cambios: false, ansi, truncado: false, ...base }
}

const sleepMs = (ms: number) => new Promise<void>((r) => setTimeout(r, ms))
const audit: TerminalAuditoria[] = []

function forcedError(): ApiError | null {
  const code = Number(new URLSearchParams(location.search).get('mockerr'))
  if (code === 409) return new ApiError(409, 'la terminal cambió, revisala de nuevo')
  if (code === 429) return new ApiError(429, 'demasiadas acciones seguidas', 23)
  if (code === 502) return new ApiError(502, 'Las terminales no respondieron: socket')
  return null
}

function find(paneId: string): Terminal {
  const t = Object.values(PLAN).flat().find((x) => x.pane_id === paneId)
  if (!t) throw new ApiError(404, 'la terminal ya no está')
  return t
}

export async function mockTerminalConfig(): Promise<TerminalConfig> {
  await sleepMs(120)
  const off = new URLSearchParams(location.search).get('escritura') === '0'
  return { escritura: !off, vivo: true, comandos_rapidos: ['git status', 'ls -la', 'docker compose ps', 'npm test'], ventana: { abierta: false, vence_en: 0, inactividad_en: 0 } }
}

export async function mockPreview(paneId: string): Promise<TerminalPreview> {
  await sleepMs(220)
  const t = find(paneId)
  const ws = Object.entries(PLAN).find(([, v]) => v.includes(t))![0]
  return {
    huella: `h-${paneId}`,
    pane_id: paneId,
    workspace: ws.split(':')[0],
    tab: ws,
    titulo: t.titulo,
    cwd: t.cwd,
    proceso: t.proceso,
    estado: t.estado,
    protegida: t.protegida,
    cierra: PLAN[ws].length > 1 ? 'terminal' : 'pestana',
    ...escritura(t),
  }
}

function record(accion: string, paneId: string, comando = '', ok = true, error = '') {
  const t = find(paneId)
  audit.unshift({ ts: new Date().toISOString(), accion, dispositivo: 'iPhone', workspace: t.titulo, proceso: t.proceso, comando, ok, error })
}

export async function mockCtrlC(paneId: string): Promise<void> {
  await sleepMs(380)
  const err = forcedError()
  if (err) {
    record('rechazo', paneId, '', false, err.detail)
    throw err
  }
  record('ctrl_c', paneId)
}

export async function mockCerrar(paneId: string): Promise<void> {
  await sleepMs(380)
  const err = forcedError()
  if (err) {
    record('rechazo', paneId, '', false, err.detail)
    throw err
  }
  record('cerrar_terminal', paneId)
  for (const k of Object.keys(PLAN)) PLAN[k] = PLAN[k].filter((t) => t.pane_id !== paneId)
}

export async function mockRepetirPreparar(paneId: string): Promise<RepetirPrep> {
  await sleepMs(420)
  const err = forcedError()
  if (err) throw err
  return { linea: 'git log --oneline -n 20', antes: '', huella2: `h2-${paneId}` }
}

export async function mockRepetirConfirmar(paneId: string, ejecutar: boolean): Promise<boolean> {
  await sleepMs(380)
  const err = forcedError()
  if (err) throw err
  if (ejecutar) record('repetir_ejecutar', paneId, 'git log --oneline -n 20')
  return ejecutar
}

export async function mockAuditoria(): Promise<TerminalAuditoria[]> {
  await sleepMs(150)
  if (!audit.length) {
    const now = Date.now()
    for (const [i, a] of ([['ctrl_c', 'npm run dev', ''], ['repetir_ejecutar', 'bash', 'docker compose ps'], ['rechazo', 'bash', '']] as const).entries())
      audit.push({ ts: new Date(now - (i + 1) * 3_600_000).toISOString(), accion: a[0], dispositivo: 'iPhone', workspace: 'Orquestador', proceso: a[1], comando: a[2], ok: a[0] !== 'rechazo', error: a[0] === 'rechazo' ? 'workspace protegido' : '' })
  }
  return audit.slice(0, 20)
}

export const MOCK_TOKEN = 'mock-token-no-es-un-secreto'

export async function mockAbrirVentana(pin: string): Promise<VentanaAbierta> {
  await sleepMs(500)
  if (!/^\d{8}$/.test(pin) || pin === '00000000') throw new ApiError(401, 'PIN incorrecto')
  return { token: MOCK_TOKEN, vence_en: 300, inactividad: 120 }
}

export async function mockComando(body: ComandoBody, token: string): Promise<void> {
  await sleepMs(420)
  if (token !== MOCK_TOKEN) throw new ApiError(401, 'abrí la escritura de nuevo')
  const err = forcedError()
  if (err) throw err
  record('comando', body.pane_id, body.comando ?? '')
}

const MOCK_CARPETAS = [
  { ruta: '~/Proyectos/orquestador', nombre: 'orquestador', repo: true },
  { ruta: '~/proyectos/acme/ps9', nombre: 'ps9', repo: true },
  { ruta: '~/Proyectos/acmekit', nombre: 'acmekit', repo: true },
]

const nuevasPorId = new Map<string, { ok: true; espacio_id: string; sesion_id: string }>()
let nuevaSeq = 0

export async function mockTerminalesCarpetas() {
  await sleepMs(120)
  return {
    carpetas: MOCK_CARPETAS,
    grupos: [
      { id: 'g1', nombre: 'orquestador', carpeta: '~/Proyectos/orquestador' },
      { id: 'g2', nombre: 'acmekit', carpeta: null },
    ],
  }
}

export async function mockTerminalesNuevaTarea(body: { id: string; repo: string; tarea: string; rama?: string }) {
  await sleepMs(400)
  const n = ++nuevaSeq
  const nombre = body.repo.split('/').pop() ?? 'repo'
  const slug = body.tarea.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'tarea'
  return { ok: true as const, pane_id: `g${n}:p1`, ruta: `${body.repo}-${slug}`, rama: body.rama || `feature/${nombre === 'orquestador' ? 'kit-' : ''}${slug}` }
}

export async function mockBorrarCopia() {
  await sleepMs(300)
  return { ok: true as const }
}

export async function mockTerminalesNueva(body: { carpeta: string; tipo: string; id: string; nombre?: string }) {
  await sleepMs(280)
  const prev = nuevasPorId.get(body.id)
  if (prev) return prev
  const n = ++nuevaSeq
  const out = { ok: true as const, espacio_id: `g${n}`, sesion_id: `g${n}:p1` }
  nuevasPorId.set(body.id, out)
  return out
}

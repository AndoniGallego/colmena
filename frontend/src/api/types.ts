import type { Estado } from '../lib/estado'
export type AgentStatus = 'idle' | 'working' | 'blocked' | 'done' | 'unknown'
export type FondoTipo = 'cursor' | 'agente' | 'comando' | 'workflow'
export interface FondoTarea {
  id: string
  tipo: FondoTipo
  texto: string
  desde: number
}
export type AgentDisplayStatus = AgentStatus | 'fondo'

export interface CtxCompact {
  ts: string
  trigger: 'auto' | 'manual'
  pre: number
  post: number
}

/** Contexto de una sesión: informativo, sin niveles de alarma. */
export interface AgentCtx {
  pct: number
  tokens: number
  window: number
  fuente: 'statusline' | 'transcript'
  compactaciones: number
  ultima_compactacion: CtxCompact | null
}

export interface Agent {
  pane_id: string
  kind: string
  status: AgentStatus
  session_id: string | null
  title: string
  doing: string
  pending: string
  /** Cierre que dejó Claude en un bloque ```estado; null si no lo escribió. */
  estado?: Estado | null
  asks_user: boolean
  /** La pregunta del último turno se marcó como leída: no pide atención hasta que haya un turno nuevo. */
  pendiente?: boolean
  /** Cuántas preguntas con opciones dejó al final; 0 si pregunta sin opciones o no pregunta. */
  preguntas?: number
  /** Terminó un turno que todavía no viste en ningún dispositivo. */
  unread?: boolean
  last_activity: string | null
  fondo?: FondoTarea[]
  /** La sesión parece trabada o en loop; el servidor la saca solo cuando se va la condición. */
  traba?: Traba
  ctx?: AgentCtx | null
  /** Tokens y costo equivalente en la API de lo que la sesión usó hoy. */
  uso?: { total: number; usd: number | null } | null
}

export type TerminalEstado = 'prompt' | 'corriendo' | 'desconocido'

export interface Terminal {
  pane_id: string
  terminal_id: string
  titulo: string
  cwd: string
  proceso: string
  estado: TerminalEstado
  protegida: boolean
}

export type TerminalMotivo = 'protegido' | 'apagada' | 'ocupada' | 'desconocido'

export interface TerminalSalida {
  puede_escribir: boolean
  motivo: TerminalMotivo | null
  sin_cambios: boolean
  revision: string
  ansi: string
  truncado: boolean
  cwd: string
  proceso: string
  estado: TerminalEstado
}

export interface TerminalVentana {
  abierta: boolean
  vence_en: number
  inactividad_en: number
}

export interface TerminalConfig {
  escritura: boolean
  vivo: boolean
  comandos_rapidos: string[]
  ventana: TerminalVentana
}

export interface TerminalPreview {
  huella: string
  pane_id: string
  workspace: string
  tab: string
  titulo: string
  cwd: string
  proceso: string
  estado: TerminalEstado
  protegida: boolean
  puede_escribir: boolean
  motivo?: TerminalMotivo | null
  /** Qué se lleva cerrarla: solo ella, su pestaña o el workspace entero. */
  cierra: TerminalCierra
}

export type TerminalCierra = 'terminal' | 'pestana' | 'espacio'

export interface VentanaAbierta {
  token: string
  vence_en: number
  inactividad: number
}

export interface ComandoBody {
  id: string
  pane_id: string
  huella: string
  comando?: string
  rapido?: number
}

export interface TerminalAccion {
  id: string
  pane_id: string
  huella: string
}

export interface RepetirPrep {
  linea: string | null
  antes: string
  huella2: string
}

export interface TerminalAuditoria {
  ts: string
  accion: string
  dispositivo: string
  workspace: string
  proceso: string
  comando: string
  ok: boolean
  error: string
}

export interface Tab {
  id: string
  label: string
  agents: Agent[]
  terminales?: Terminal[]
}

export interface Workspace {
  id: string
  number: number
  label: string
  /** Protegido: va siempre primero en el tablero. */
  pinned?: boolean
  status: AgentStatus
  tabs: Tab[]
}

export interface Board {
  updated_at: string
  focused_tab_id: string | null
  self_pane_id: string | null
  workspaces: Workspace[]
  terminales: 'ok' | 'sin_conexion'
  conflictos: string[]
  /** Backends de terminales propias que no responden (p. ej. `guardian`). */
  caidos: string[]
}

export interface DigestTurn {
  role: 'user' | 'claude'
  text: string
}

export interface Digest {
  title: string
  last_prompt: string
  turns: DigestTurn[]
}

export interface TranscriptFoto {
  id: string
}

export interface TranscriptItem {
  /** Posición absoluta en el transcript; el servidor la manda aunque descarte ítems. */
  idx?: number
  kind: 'user' | 'claude' | 'tool' | 'compact' | 'imagenes'
  text: string
  name: string
  summary: string
  ts: string
  /** Disparador y tamaños de la compactación que cerró este tramo. */
  compact?: { trigger: 'auto' | 'manual'; pre: number; post: number }
  /** Ids de la Biblioteca de lo que publicó o mandó esta línea. */
  lib_ids?: string[]
  /** Ruta absoluta de una captura citada en un bloque pruebas -> id de la Biblioteca. */
  evidencias?: Record<string, string>
  /** Id del mensaje que trae bloques ```comando y posición del primero de este ítem dentro de ese mensaje. */
  cmid?: string
  cstart?: number
  /** cwd real de la sesión en ese mensaje (donde corre un `!`). */
  ccwd?: string
  /** Grupo de capturas embebidas en resultados de herramientas. */
  fotos?: TranscriptFoto[]
}

export type CtxLevel = 'ok' | 'caution' | 'warn' | 'unknown'

export interface StatusLine {
  model: string
  ticket: string
  ctx_pct: number | null
  ctx_level: CtxLevel
  vpn: 'up' | 'down' | null
}

export interface TranscriptPage {
  items: TranscriptItem[]
  before: number | null
  title: string
  status: AgentStatus
  pane_id: string
  status_line: StatusLine
}

export interface Upload {
  id: string
  name: string
  size: number
  kind: 'image' | 'pdf' | 'text'
}

export interface VozEstado {
  habilitada: boolean
  modelo: string
  cargado: boolean
  ocupada: boolean
  max_segundos: number
}

export interface VozResultado {
  texto: string
  duracion: number
  proceso: number
}

export interface SessionEvent {
  session_id: string
  mtime: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'event' | 'reporte'
  text: string
  ts?: string
  /** `vigia`: generado por el servidor sin LLM (fin de frente, propuestas); la UI lo marca con "Vi esto". */
  origen?: 'vigia'
  /** Un aviso del servidor está asociado a este mensaje (el botón "Vi esto" lo marca). */
  aviso?: boolean
  visto?: boolean
  /** Separator the server adds when Centinela starts a fresh conversation; `respuesta` is a reply sent from the stepper. */
  kind?: 'nueva' | 'respuesta'
  /** The session a `respuesta` went to. */
  session_id?: string
  /** Sessions that finished a turn, in a `reporte`. */
  items?: ReporteFila[]
  /** Rows beyond the ones shown. */
  mas?: number
  /** Memory searches Centinela ran during the turn. */
  pasos?: PasoMemoria[]
  /** Upload ids the user attached; Centinela reads them, never writes them. */
  adjuntos?: string[]
}

export interface ReporteFila {
  session_id: string
  pane_id: string
  nombre: string
  donde: string
  pedido: string
  quedo: string
  pregunta: string
  cadena: boolean
  plan_id: string
  fin: string
}

export interface PasoMemoria {
  name: string
  summary: string
}

export type EngramEstado = 'ok' | 'caido' | 'deshabilitado'

export interface MemoriaEstado {
  habilitada: boolean
  indexados: number
  turnos: number
  tamano_mb: number
  ultima_actualizacion: string | null
  actualizando: boolean
  engram: EngramEstado
}

export type MemoriaCita =
  | { tipo: 'sesion'; session_id: string; turno: number; titulo: string; fecha: string; rol: string; texto: string }
  | { tipo: 'engram'; id: number; texto: string }

export type MemoriaCitaRef = { tipo: 'sesion'; session_id: string; turno: number } | { tipo: 'engram'; id: number }

export interface DiosTokens {
  input: number
  cache_write: number
  cache_read: number
  output: number
  mensajes: number
  total: number
}

export interface DiosDia extends DiosTokens {
  fecha: string
}

/** `escrito`: typed in the composer; `opcion`: a button, option or suggestion picked. */
export type ChatOrigen = 'escrito' | 'opcion'

export interface MensajeRequest {
  id: string
  pane_id: string
  texto: string
  adjuntos?: string[]
  origen: 'manual' | 'jefe'
  destino: string
  por_que: string
}

export interface MensajeResult {
  ok: boolean
  pane_id: string
  event: ChatMessage | null
}

export type CloseTipo = 'tab' | 'workspace'

export interface ClosePane {
  pane_id: string
  kind: string | null
  status: AgentStatus | null
  titulo: string
  session_id: string | null
  cwd: string
  proceso: string | null
}

export interface CloseBlocker {
  pane_id: string
  status: AgentStatus
}

export interface ClosePreview {
  tipo: CloseTipo
  target_id: string
  label: string
  workspace_label: string
  cierra_workspace: boolean
  tab_count: number
  panes: ClosePane[]
  bloqueantes: CloseBlocker[]
  huella: string
}

export interface CloseRequest {
  id: string
  tipo: CloseTipo
  target_id: string
  huella: string
  origen: 'manual' | 'jefe'
  destino: string
  por_que: string
  sin_guardar?: boolean
  forzar?: boolean
}

export type GuardadoPaneEstado = 'guardando' | 'listo' | 'bloqueado' | 'fallo'
export type GuardadoTargetEstado = 'guardando' | 'cerrando' | 'cerrado' | 'error' | 'cancelado'

export interface GuardadoPane {
  pane_id: string
  titulo: string
  estado: GuardadoPaneEstado
}

export interface GuardadoTarget {
  key: string
  tipo: string
  target_id: string
  label: string
  estado: GuardadoTargetEstado
  error: string
  guardado: string
  panes: GuardadoPane[]
  /** once closed: the sessions that went away (for the "resume" commands) */
  sesiones: CloseSession[]
  copias?: CopiaCierre[]
}

/** A closure waiting for the sessions to save to Engram: one lote = one or more targets sharing a timeout. */
export interface Guardado {
  id: string
  origen: string
  plan_id: string
  vencido: boolean
  puede_cerrar_igual: boolean
  terminado: boolean
  targets: GuardadoTarget[]
}

/** What the live board stream can tell the app; only the first two are required. */
export interface BoardHandlers {
  onBoard: (b: Board) => void
  onState: (s: ConnectionState) => void
  onSession?: (e: SessionEvent) => void
  onLibrary?: (ids: string[]) => void
  onBuild?: (id: string) => void
  onAviso?: (id: number) => void
  onAvisosLeidos?: (tags: string[]) => void
  onMrs?: (version: number) => void
  onNotas?: (d: { version: number; pendientes: number }) => void
  onPermisos?: (pedidos: PedidoPermiso[]) => void
  onGuardado?: (g: Guardado) => void
  onAbrirTerminal?: (e: { pane_id: string; titulo: string }) => void
  onPedidoPestana?: (e: { id: string; estado: PedidoPestanaEstado }) => void
  onOrdenTablero?: (orden: string[]) => void
  onOrdenPestanas?: (e: { grupo: string; orden: string[] }) => void
  onPlegadas?: (plegadas: string[]) => void
  onSilenciadas?: (silenciadas: string[]) => void
  onNudo?: (orden: unknown, device: string) => void
  /** Evento `guia` de la guía por atajo (G2); solo llega a la PC dueña. */
  onGuia?: (data: unknown, device: string) => void
  /** Eventos `reunion-*` del copiloto de reuniones; `device` es el id de esta conexión. */
  onReunion?: (evento: string, data: unknown, device: string) => void
  /** La conexión de la app de Windows (`pc=1`) quedó abierta, la primera vez y cada reconexión. */
  onPcListo?: (device: string) => void
}

export type OrdenTableroData = { orden: string[]; pestanas: Record<string, string[]>; plegadas: string[]; silenciadas: string[] }

export type PedidoPestanaEstado = 'pendiente' | 'abierto' | 'rechazado' | 'vencido' | 'descartado'

export interface PedidoPestanaOrigen {
  pane_id: string
  nombre: string
  /** Sesión que pidió; '' si el pedido no la trae. */
  session_id: string
}

export type PedidoPestanaTipo = 'claude' | 'terminal'

export interface PedidoPestanaTab {
  nombre: string
  tipo: PedidoPestanaTipo
  carpeta: string
  mensaje?: string
  comando?: string
}

/** La terminal común que una sesión pidió cerrar (así estaba en el tablero cuando la pidió). */
export interface PedidoPestanaTerminal {
  pane_id: string
  titulo: string
  cwd: string
  proceso: string
  estado: string
  donde: string
}

export type ObjetivoCierre = 'sesion' | 'pestana' | 'tarjeta'

/** Lo que un pedido de cierre quiere cerrar: una sesión, una pestaña o una tarjeta entera. */
export interface PedidoPestanaCierre {
  objetivo: ObjetivoCierre
  tipo: 'tab' | 'workspace'
  target_id: string
  label: string
  workspace_label: string
  carpeta: string
  sesiones: number
  terminales: number
}

export interface VistaCierrePedido {
  trabajando: boolean
  estados: string[]
  huella: string
}

export interface PedidoPestana {
  id: string
  carpeta: string
  mensaje: string
  nombre?: string
  tarjeta?: string
  pestanas?: PedidoPestanaTab[]
  /** Sin acción, el pedido abre pestañas; 'cerrar' pide cerrar `terminal`; 'cursor' pide un trabajador Cursor.
   *  'mensaje', 'programada' y 'tarea' los pide una sesión por el MCP de Colmena. */
  accion?: 'cerrar' | 'cursor' | 'mensaje' | 'programada' | 'tarea'
  terminal?: PedidoPestanaTerminal
  /** Con accion 'cerrar' de sesión, pestaña o tarjeta (sin `terminal`). */
  cierre?: PedidoPestanaCierre
  /** Solo con accion 'cursor': `nombre` es la etiqueta, `mensaje` el pedido y `carpeta` el repo. */
  cursor?: { modelo?: string }
  /** accion 'mensaje': sesión destino; `mensaje` es el texto. */
  envio?: { pane_id: string; nombre: string }
  /** accion 'programada': hora HH:MM y sesión destino; `mensaje` es el texto. */
  programada?: { cuando: string; pane_id: string; nombre: string }
  /** accion 'tarea': ticket; `carpeta` es el repo y `mensaje` la nota. */
  tarea?: { ticket: string }
  /** La sesión que pide leyó otra sesión antes de este pedido (últimos 30 min). */
  leyo_otra_sesion?: { nombre: string; ts: number }
  origen: PedidoPestanaOrigen
  ts: number
  vence: number
}

export interface AbrirPedidoPestanaResult {
  ok: true
  pane_id: string
  pane_ids?: string[]
  pegado?: boolean
  /** El pedido era cerrar una terminal y se cerró. */
  cerrada?: boolean
  /** El cierre pidió guardar primero y quedó esperando; `pane_id` viene vacío. */
  guardando?: boolean
}

export type GuardadoAccion = 'cerrar_igual' | 'esperar_mas'

export interface CloseSession {
  session_id: string | null
  cwd: string
  titulo: string
}

/** Copia del repo que creó Colmena para una tarea, y si se puede borrar sin perder trabajo. */
export interface CopiaCierre {
  ruta: string
  rama: string
  borrable: boolean
  motivo: string
}

export interface CloseResult {
  ok: boolean
  sesiones: CloseSession[]
  copias?: CopiaCierre[]
  event: ChatMessage | null
  aviso?: string
  /** the closure went out as "guardando": sessions were asked to save first */
  guardando?: Guardado
}

export type LimpiezaRazon =
  | { tipo: 'quieto'; dias: number }
  | { tipo: 'sin_claude'; dias: number }
  | { tipo: 'mergeada'; rama: string; base: string }

export type LimpiezaBloqueo = 'corriendo' | 'sin_leer'

export interface LimpiezaSesion {
  session_id: string
  titulo: string
  ultima: string | null
  pendiente: string
}

export interface LimpiezaItem {
  tipo: CloseTipo
  target_id: string
  workspace: string
  label: string
  razones: LimpiezaRazon[]
  sesiones: LimpiezaSesion[]
  terminales: number
  marcado: boolean
  bloqueado: LimpiezaBloqueo | null
}

export interface LimpiezaCandidatos {
  dias: number
  items: LimpiezaItem[]
  generado_at: string
  git: 'ok' | 'parcial' | 'sin_datos'
}

export interface LimpiezaPreviewItem {
  tipo: CloseTipo
  target_id: string
  preview: ClosePreview | null
  error: string
  bloqueantes: CloseBlocker[]
}

export interface LimpiezaEjecutarBody {
  lote_id: string
  dias: number
  items: { id: string; tipo: CloseTipo; target_id: string; huella: string }[]
  sin_guardar?: boolean
}

export interface LimpiezaResultado {
  target_id: string
  ok: boolean
  error: string
  sesiones: CloseSession[]
}

export interface LimpiezaHandlers {
  onItem: (r: LimpiezaResultado) => void
  onFin: (f: { cerrados: number; salteados: number }) => void
  onGuardando?: (g: Guardado) => void
}

export type DialogChoice = 'si' | 'si_siempre' | 'si_auto' | 'si_ediciones' | 'no'

export interface PermisoView {
  herramienta: 'Bash' | 'Write' | 'Edit'
  detalle: string
  descripcion: string
  completo: boolean
  opciones: DialogChoice[]
  regla: string | null
  mas_en_terminal: boolean
  archivo: string
  replace_all: boolean
}

export interface PreguntaOpcion {
  label: string
  descripcion: string
}

export interface PreguntaItem {
  header: string
  texto: string
  multi: boolean
  otro: boolean
  opciones: PreguntaOpcion[]
}

export interface PreguntaView {
  preguntas: PreguntaItem[]
}

export type CategoriaPermiso = 'auto' | 'gris' | 'usuario'

export type EstadoPedido = 'abierto' | 'enviando' | 'permitido' | 'rechazado' | 'siempre' | 'terminal' | 'vencido' | 'dialogo'

export interface ReglaPedido {
  herramienta: string
  contenido: string
  archivo: string
  huella: string
}

export interface PedidoPermiso {
  id: string
  session_id: string
  pane_id: string
  herramienta: string
  entrada: Record<string, unknown>
  estado: EstadoPedido
  /** Cuándo quedó abierto el pedido (ISO). */
  creado?: string | null
  regla: ReglaPedido | null
  categoria?: CategoriaPermiso | null
  regla_politica?: string | null
  motivo_politica?: string | null
}

export interface RegistroPermiso {
  hora?: string
  categoria?: CategoriaPermiso | null
  regla_politica?: string | null
  motivo_politica?: string | null
  motivo_centinela?: string | null
  herramienta?: string
  entrada?: Record<string, unknown>
  pane_id?: string
  session_id?: string
  sesion?: string | null
  tool_use_id?: string
  encargo_id?: string
  quien?: 'politica' | 'usuario' | 'centinela'
  decision?: 'permitir' | 'rechazar' | 'siempre'
  objecion?: { nota: string; hora?: string }
}

export interface DecidirPermisoRequest {
  accion: 'permitir' | 'rechazar' | 'siempre'
  motivo?: string
  pin?: string
  huella_regla?: string
}

export type DialogView =
  | { tipo: 'ninguno' }
  | { tipo: 'desconocido'; paneId: string; pantalla: string }
  | { tipo: 'permiso'; huella: string; paneId: string; permiso: PermisoView }
  | { tipo: 'pregunta'; huella: string; paneId: string; pregunta: PreguntaView }
  | { tipo: 'pedido'; pedido: PedidoPermiso }

export interface DialogAnswerRequest {
  id: string
  session_id: string
  pane_id: string
  huella: string
  tipo: 'permiso' | 'pregunta'
  permiso?: DialogChoice
  pin?: string
  respuestas?: { opciones?: number[]; otro?: string }[]
}

export interface DialogAnswerResult {
  ok: boolean
  interrumpida: boolean
}

export type ConnectionState = 'connecting' | 'live' | 'reconnecting'

export interface PreguntaSesion {
  sig: string
  session_id: string
  pane_id: string
  nombre: string
  preguntas: { pregunta: string; opciones: { label: string; detalle: string; recomendada: boolean }[] }[]
}

export interface RespuestaPreguntaRequest {
  id: string
  sig: string
  texto: string
}

export interface ConfianzaPreparar {
  repo: string
  base: string
  origen: string
  setup_toml: string
  setup_sha256: string
  script: string | null
  script_contenido: string | null
  script_sha256: string | null
  copiar: string[]
  puertos: number
  docker: boolean
}

export interface PrepararResumen {
  puerto: number | null
  puertos: number
  copiados: string[]
  omitidos: string[]
  setup_pane_id?: string
  puertos_fijos?: boolean
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
    public retryAfter: number | null = null,
    public bloqueantes: CloseBlocker[] = [],
    public sinCuerpo?: boolean,
    public codigo?: string,
    public confianza?: ConfianzaPreparar,
  ) {
    super(detail)
  }
}

export type LibKind = 'html' | 'image' | 'svg' | 'gif' | 'pdf' | 'video' | 'text' | 'diagrama' | 'pruebas' | 'reunion' | 'remoto' | 'otro'

export interface LibItem {
  id: string
  kind: LibKind
  source: string
  session_id: string
  session_titulo: string
  project: string
  subagent: string
  ts: string
  title: string
  description: string
  caption: string
  nombre: string
  donde: string
  exists: boolean
  copia: boolean
  servible: boolean
  motivo: string
  size: number
  mime: string
  url: string
  version: number
  versions: { version: number; ts: string }[]
  diagrama_raw: string
  /** Informe de pruebas en JSON (solo kind 'pruebas'). */
  pruebas_raw?: string
  /** Reunión guardada en JSON (solo kind 'reunion'): fechas como epoch en segundos. */
  reunion_raw?: string | null
  /** La charla completa sigue en disco (se borra a los 90 días). */
  tiene_charla?: boolean
  /** ruta de la captura -> id de la Biblioteca */
  evidencias?: Record<string, string>
  /** URL del visor con token de 30 minutos; vacía si el ítem no se sirve. */
  src: string
  vecinos?: { anterior: string | null; siguiente: string | null }
}

export interface LibFilters {
  tipo: LibKind[]
  session: string
  desde: string
  hasta: string
  q: string
}

export interface LibListing {
  items: LibItem[]
  cursor: string | null
  indexando: boolean
  total: number
}

export interface LibSession {
  session_id: string
  titulo: string
  proyecto: string
  n: number
  ultimo_ts: string
}

export type SubagenteEstado = 'trabajando' | 'termino' | 'sin_actividad'

export interface Subagente {
  id: string
  descripcion: string
  tipo: string
  modelo: string
  estado: SubagenteEstado
  inicio: string
  segundos: number
  paso: string
  tokens: number | null
}

export type TrabaTipo = 'repetida' | 'fallando' | 'colgada' | 'quieta'

export interface Traba {
  tipo: TrabaTipo
  /** Segundos desde epoch. */
  desde: number
  detalle: string
}

export type AvisoKindBase = 'asks' | 'blocked' | 'done' | 'terminal' | 'cierre' | 'encadenar' | 'vigia' | 'mr' | 'entorno' | 'test' | 'progreso' | 'pestana' | 'trabada'
/** Los del núcleo más los que registran las piezas montadas. */
export type AvisoKind = AvisoKindBase | (string & {})

export interface Aviso {
  id: number
  ts: number
  kind: AvisoKind
  titulo: string
  cuerpo: string
  session_id: string
  pane_id: string
  fecha: string
  /** `<project_id>:<iid>` en los avisos de MRs. */
  mr: string
  mensaje?: string
  /** Pedido de pestaña asociado (uuid). */
  pedido?: string
  /** Aviso generado solo para probar el notch; no entra en la campana ni en el contador. */
  prueba?: boolean
  entregado: boolean
  leido: boolean
  motivo: string
  tag: string
}

/** Una sola condición: los avisos de esa sesión, terminal o tipo. */
export type FiltroAvisos = { session_id: string } | { pane_id: string } | { kind: AvisoKind } | { mr: string } | { mensaje: string }
export type FiltroCierre = FiltroAvisos | { tags: string[] }

export interface AvisosPage {
  items: Aviso[]
  hayMas: boolean
  noLeidos: number
  leidosHasta: number
}

export interface SubscribeOpts {
  presencia?: boolean
  /** La página del notch dentro de la app de Windows atiende las órdenes del nudo. */
  pcNudo?: boolean
  /** Si el cliente es Colmena de escritorio (evita import circular con viewport). */
  escritorio?: () => boolean
}

export type AbrirEnPcResult = { ok: true } | { ok: false; motivo: 'sin_pc' }

export interface Api {
  login(pin: string): Promise<void>
  getBoard(): Promise<Board>
  getOrdenTablero(): Promise<OrdenTableroData>
  setOrdenTablero(orden: string[]): Promise<void>
  getAtajos(): Promise<Record<string, string>>
  setAtajos(atajos: Record<string, string>): Promise<void>
  setPlegadas(plegadas: string[]): Promise<void>
  setSilencio(sid: string, on: boolean): Promise<void>
  irAPc(sid: string): Promise<void>
  setOrdenPestanas(grupo: string, orden: string[]): Promise<void>
  subscribeBoard(handlers: BoardHandlers, opts?: SubscribeOpts): () => void
  accionGuardado(loteId: string, accion: GuardadoAccion): Promise<Guardado>
  getAvisos(limite?: number, antes?: number, incluirPrueba?: boolean): Promise<AvisosPage>
  getPedidosPestana(): Promise<PedidoPestana[]>
  abrirPedidoPestana(id: string, opciones?: { huella?: string; forzar?: boolean }): Promise<AbrirPedidoPestanaResult>
  vistaCierrePedido(id: string): Promise<VistaCierrePedido>
  rechazarPedidoPestana(id: string): Promise<{ ok: true }>
  marcarAvisosLeidos(hasta: number, endpoint?: string): Promise<number>
  marcarAvisosDe(filtro: FiltroAvisos, endpoint?: string): Promise<number>
  getDigest(sessionId: string, turns?: number): Promise<Digest>
  getTranscript(sessionId: string, before?: number | null, limit?: number, desde?: number | null): Promise<TranscriptPage>
  getSubagentes(sessionId: string): Promise<Subagente[]>
  uploadFile(file: File, onProgress: (fraction: number) => void, signal: AbortSignal): Promise<Upload>
  getVozEstado(): Promise<VozEstado>
  transcribirVoz(audio: Blob, signal: AbortSignal): Promise<VozResultado>
  abrirEnPc(paneId: string, titulo: string): Promise<AbrirEnPcResult>
  markSeen(sessionId: string): Promise<void>
  /** Da por leída la pregunta del turno actual (pasa a Pendiente). */
  marcarPreguntaVista(sessionId: string): Promise<void>
  getClaudeUso(): Promise<import('../lib/usoClaude').ClaudeUso>
  proponerVariante(body: Record<string, string>): Promise<ChatMessage>
  executeMensaje(body: MensajeRequest): Promise<MensajeResult>
  stopSession(paneId: string): Promise<void>
  previewClose(tipo: CloseTipo, targetId: string): Promise<ClosePreview>
  executeClose(body: CloseRequest): Promise<CloseResult>
  getDialog(sessionId: string): Promise<DialogView>
  getPregunta(sessionId: string): Promise<PreguntaSesion>
  responderPregunta(sessionId: string, body: RespuestaPreguntaRequest): Promise<{ ok: boolean }>
  correrComando(sessionId: string, body: { mid: string; indice: number; comando: string }): Promise<{ ok: boolean; comando: string; cwd?: string }>
  answerDialog(body: DialogAnswerRequest): Promise<DialogAnswerResult>
  decidirPermiso(id: string, req: DecidirPermisoRequest): Promise<PedidoPermiso>
  getPermisos(): Promise<{ pedidos: PedidoPermiso[] }>
  getPermisosRegistro(): Promise<{ items: RegistroPermiso[] }>
  getHandoff(name: string): Promise<string>
  revokeAll(): Promise<void>
  getLibrary(filters: LibFilters, cursor?: string | null, limit?: number): Promise<LibListing>
  getLibraryItem(id: string, filters?: LibFilters): Promise<LibItem>
  getLibrarySessions(): Promise<LibSession[]>
  getLibraryText(id: string): Promise<string>
  getLibraryCharla(id: string): Promise<string>
  quitarLibrary(ids: string[]): Promise<number>
  getTerminalSalida(paneId: string, rev: string, signal: AbortSignal): Promise<TerminalSalida>
  getTerminalConfig(): Promise<TerminalConfig>
  getTerminalesCarpetas(): Promise<{ carpetas: { ruta: string; nombre: string; repo?: boolean }[]; grupos: { id: string; nombre: string; carpeta: string | null }[] }>
  postTerminalesNuevaTarea(body: { id: string; repo: string; tarea: string; nombre?: string; rama?: string }): Promise<{ ok: true; pane_id: string; ruta: string; rama: string; pegado?: false; preparar?: PrepararResumen }>
  postTerminalesNuevaTareaConfiar(body: { repo: string; setup_sha256: string; script_sha256: string | null }): Promise<{ ok: true }>
  postBorrarCopia(ruta: string): Promise<{ ok: true }>
  postTerminalesNueva(body: { carpeta: string; tipo: 'shell' | 'claude'; id: string; nombre?: string; grupo?: string }): Promise<{ ok: true; espacio_id: string; sesion_id: string }>
  getSesionesViejas(qs?: string): Promise<{ session_id: string; titulo: string; carpeta: string; ultimo_ts: string; ultima_frase: string }[]>
  postSesionesViejasRetomar(body: {
    id: string
    session_id: string
    nombre?: string
    grupo?: string
    nombre_tarjeta?: string
  }): Promise<{ ok: true; espacio_id: string; sesion_id: string; pane_id?: string }>
  previewTerminal(paneId: string): Promise<TerminalPreview>
  terminalCtrlC(body: TerminalAccion): Promise<void>
  /** Cierra una terminal común (nunca una sesión de Claude). Sola en su pestaña, se cierra la pestaña. */
  cerrarTerminal(body: TerminalAccion): Promise<void>
  /** Renombra un grupo (g1) o una pestaña (g1:t1) del guardián. */
  renombrarTerminal(body: { tipo: 'grupo' | 'pestana'; id: string; nombre: string }): Promise<void>
  listarNotas(): Promise<{ notas: Nota[]; pendientes: number; version: number }>
  crearNota(b: { tipo: TipoNota; texto: string; origen?: OrigenNota }): Promise<Nota>
  editarNota(id: string, b: { texto?: string; tipo?: TipoNota; hecha?: boolean }): Promise<Nota>
  borrarNota(id: string): Promise<void>
  repetirPreparar(body: TerminalAccion): Promise<RepetirPrep>
  repetirConfirmar(body: { id: string; pane_id: string; huella2: string; ejecutar: boolean }): Promise<boolean>
  getTerminalAuditoria(limit: number): Promise<TerminalAuditoria[]>
  abrirVentana(pin: string): Promise<VentanaAbierta>
  cerrarVentana(token: string, keepalive?: boolean): Promise<void>
  enviarComando(body: ComandoBody, token: string): Promise<void>
  getLimpieza(dias?: number | null): Promise<LimpiezaCandidatos>
  previewLimpieza(items: { tipo: CloseTipo; target_id: string }[]): Promise<LimpiezaPreviewItem[]>
  ejecutarLimpieza(body: LimpiezaEjecutarBody, handlers: LimpiezaHandlers, signal: AbortSignal): Promise<void>
  getMemoriaEstado(): Promise<MemoriaEstado>
  reindexarMemoria(): Promise<void>
  borrarMemoria(): Promise<void>
  getMemoriaCita(ref: MemoriaCitaRef): Promise<MemoriaCita>
}

export type TipoNota = 'recordatorio' | 'apunte'
export interface OrigenNota {
  sid: string
  nombre: string
  ts: string
}
export interface Nota {
  id: string
  tipo: TipoNota
  texto: string
  hecha_at: string | null
  creada_at: string
  editada_at: string
  origen: OrigenNota | null
}

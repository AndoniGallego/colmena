import { toPasos, type DiagramaPasos } from './pasos'

/** Fence name that older messages used for secuencias and procesos. It is read as a diagrama and never shown. */
export const LEGACY_FENCE = 'flujo'

/** Old bodies may lack "tipo": it was inferred from the actors, which `toPasos` still does. */
export const diagramaLegado = (value: unknown): DiagramaPasos | null => toPasos(value)

/** The fence name as the rest of the app knows it. */
export const fenceCanonico = (nombre: string) => (nombre.toLowerCase() === LEGACY_FENCE ? 'diagrama' : nombre.toLowerCase())

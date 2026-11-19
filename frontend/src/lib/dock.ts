import type { Opciones } from './opciones'
import { pendingLabel } from './stepper'

/** One set of questions in a session's dock. */
export interface LoteDock {
  /** progress is saved under it */
  key: string
  sig: string
  questions: Opciones[]
}

/** What the chip says once the card was put away. */
export const chipLabel = (lotes: LoteDock[]): string => pendingLabel(lotes.reduce((n, l) => n + l.questions.length, 0))

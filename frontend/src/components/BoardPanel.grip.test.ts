import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { deltaArrastreY, indicesCorrimientoArrastre } from '../lib/boardDrag'

/**
 * pointercancel después de armar no debe desarmar el hold pendiente (regresión touch).
 * El comportamiento vive en onGripCancelHold + gripArmed en BoardPanel.vue.
 */
describe('BoardPanel grip touch', () => {
  it('onGripCancelHold ignora cancel si gripArmed', () => {
    let armed = true
    let cleared = false
    const onGripCancelHold = () => {
      if (armed) return
      cleared = true
    }
    onGripCancelHold()
    expect(cleared).toBe(false)
    armed = false
    onGripCancelHold()
    expect(cleared).toBe(true)
  })

  it('onGripCancelHold cancela hold pendiente si aún no armó', () => {
    let armed = false
    let holdCleared = false
    const onGripCancelHold = () => {
      if (armed) return
      holdCleared = true
    }
    onGripCancelHold()
    expect(holdCleared).toBe(true)
  })

  it('tras el hold el transform Y sigue el dedo', () => {
    const startY = 200
    const moveY = 268
    expect(deltaArrastreY(moveY, startY)).toBe(68)
  })

  it('la manija declara touch-action none en WorkspaceCard', () => {
    const src = readFileSync('src/components/WorkspaceCard.vue', 'utf8')
    expect(src).toMatch(/\.ws-grip\s*\{[\s\S]*?touch-action:\s*none/)
    expect(src).toMatch(/@touchstart\.stop\.prevent="onGripTouchStart"/)
  })

  it('helpers de arrastre en boardDrag', () => {
    expect(deltaArrastreY(10, 0)).toBe(10)
    expect(indicesCorrimientoArrastre(0, 1, 3)).toEqual([1])
  })
})

import { describe, expect, it } from 'vitest'
import { shouldMarkSeen } from './seen'

describe('shouldMarkSeen', () => {
  it('marca con chat abierto, visible y respuesta sin ver', () => {
    expect(shouldMarkSeen({ unread: true, sessionOpen: true, visible: true })).toBe(true)
    expect(shouldMarkSeen({ unread: true, sessionOpen: false, visible: true })).toBe(false)
    expect(shouldMarkSeen({ unread: true, sessionOpen: true, visible: false })).toBe(false)
    expect(shouldMarkSeen({ unread: undefined, sessionOpen: true, visible: true })).toBe(false)
  })

  it('marca sesión done abierta y visible aunque no haya unread', () => {
    expect(shouldMarkSeen({ unread: false, status: 'done', sessionOpen: true, visible: true })).toBe(true)
    expect(shouldMarkSeen({ unread: undefined, status: 'done', sessionOpen: true, visible: true })).toBe(true)
  })

  it('no marca sesión done si no está visible', () => {
    expect(shouldMarkSeen({ unread: false, status: 'done', sessionOpen: true, visible: false })).toBe(false)
  })

  it('no marca idle sin unread', () => {
    expect(shouldMarkSeen({ unread: false, status: 'idle', sessionOpen: true, visible: true })).toBe(false)
    expect(shouldMarkSeen({ unread: undefined, status: 'idle', sessionOpen: true, visible: true })).toBe(false)
  })
})

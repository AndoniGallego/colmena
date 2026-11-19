import postcss from 'postcss'
import { describe, expect, it } from 'vitest'
import hoverSoloMouse from './hoverSoloMouse'

const run = (css: string) => postcss([hoverSoloMouse()]).process(css, { from: undefined }).css
const norm = (s: string) => s.replace(/\s+/g, ' ').replace(/ ?([{}]) ?/g, '$1').trim()
const MQ = '@media (hover: hover) and (pointer: fine)'

describe('hoverSoloMouse', () => {
  it('envuelve una regla con :hover', () => {
    expect(norm(run('.a:hover{color:red}'))).toBe(`${MQ}{.a:hover{color:red}}`)
  })

  it('no duplica una regla ya dentro de hover: hover', () => {
    const css = `${MQ}{.a:hover{color:red}}`
    expect(norm(run(css))).toBe(norm(css))
  })

  it('no toca :not(:hover)', () => {
    expect(run('.a:not(:hover){color:red}')).toBe('.a:not(:hover){color:red}')
  })

  it('separa selectores con y sin :hover', () => {
    const out = norm(run('.a, .b:hover {color:red}'))
    expect(out).toContain('.a{color:red}')
    expect(out).toContain(`${MQ}{.b:hover{color:red}}`)
    expect(out.indexOf('.a{')).toBeLessThan(out.indexOf('@media'))
  })

  it('anida dentro de un @media padre', () => {
    const out = norm(run('@media (max-width: 700px){.a:hover{color:red}}'))
    expect(out).toBe(`@media (max-width: 700px){${MQ}{.a:hover{color:red}}}`)
  })

  it('no toca :focus-visible ni :active', () => {
    const css = '.a:focus-visible{outline:0}.b:active{opacity:.9}'
    expect(run(css)).toBe(css)
  })

  it('no toca reglas dentro de @keyframes', () => {
    const css = '@keyframes k{from{opacity:0}to{opacity:1}}'
    expect(run(css)).toBe(css)
  })
})

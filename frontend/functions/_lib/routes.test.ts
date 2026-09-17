/**
 * The Functions routing contract.
 *
 * Without a committed `_routes.json`, Pages invokes a Function on **every**
 * request once a `functions/` directory exists. The character-preview handler
 * answers HTML requests by fetching the root shell, so routing every path
 * through it means `/assets/*.js` and same-origin JSON calls came back as
 * HTML — and the browser failed with "JSON.parse: unexpected character at
 * line 1 column 1", which is exactly what shipped once.
 *
 * The route list must therefore stay scoped to the one path the function
 * serves. This test exists so widening it is a deliberate act, not a side
 * effect of editing the file.
 */
import { describe, expect, it } from 'vitest'
import routes from '../../public/_routes.json'

describe('_routes.json', () => {
  it('invokes Functions only for character pages', () => {
    expect(routes.include).toEqual(['/character/*'])
  })

  it('excludes nothing, because the include list is already narrow', () => {
    expect(routes.exclude).toEqual([])
  })

  it('declares the current schema version', () => {
    expect(routes.version).toBe(1)
  })
})

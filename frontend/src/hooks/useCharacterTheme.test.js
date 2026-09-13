/**
 * The hook is a memoised pure derivation now — the server measures the seed,
 * the hook only turns it into tokens — so what is worth pinning is the
 * contract the page depends on: no seed, no theme; same seed, same theme
 * object; a seed the extractor declined (too grey) behaves like no seed.
 */
import { renderHook } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useCharacterTheme } from './useCharacterTheme'

describe('useCharacterTheme', () => {
  it('returns null before any seed has arrived', () => {
    const { result } = renderHook(() => useCharacterTheme('Lucy', null))
    expect(result.current).toBeNull()
  })

  it('returns null without a character, seed or not', () => {
    const { result } = renderHook(() => useCharacterTheme(null, '#aeb7d2'))
    expect(result.current).toBeNull()
  })

  it('derives a theme from the seed', () => {
    const { result } = renderHook(() => useCharacterTheme('Lucy', '#aeb7d2'))
    expect(result.current).not.toBeNull()
    expect(result.current.light.accent).toMatch(/^#[0-9a-f]{6}$/)
    expect(result.current.dark.accent).toMatch(/^#[0-9a-f]{6}$/)
  })

  it('returns the same theme object for the same seed across mounts', () => {
    // The derivation is memoised per seed: eighty characters mounting in a
    // session must not re-derive eighty times, and the page must not see a new
    // theme identity (and repaint every --char-* property) on each render.
    const first = renderHook(() => useCharacterTheme('Lucy', '#aeb7d2'))
    const second = renderHook(() => useCharacterTheme('Lucy (EL)', '#aeb7d2'))
    expect(second.current).toBe(first.current)
  })

  it('follows the seed when the gallery response refreshes it', () => {
    const { result, rerender } = renderHook(({ seed }) => useCharacterTheme('Audrey Hall', seed), {
      initialProps: { seed: '#9f8c44' },
    })
    const before = result.current
    rerender({ seed: '#3f7a4f' })
    expect(result.current).not.toBe(before)
    expect(result.current).not.toBeNull()
  })

  it('treats a declined seed as no theme at all', () => {
    // A grey the extractor should never have stored; the page keeps the
    // system accent rather than theming itself with mud.
    const { result } = renderHook(() => useCharacterTheme('2B', '#808080'))
    expect(result.current).toBeNull()
  })
})

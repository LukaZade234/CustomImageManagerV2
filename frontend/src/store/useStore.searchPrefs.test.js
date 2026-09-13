/**
 * The remembered filter choices.
 *
 * "The last thing you picked is there next time" is a claim about a fresh
 * module load, so these tests wipe storage, drop the module registry, and
 * import the store again — otherwise they would only prove that the in-memory
 * copy keeps what was set, which was already true before it persisted.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

describe('remembered search preferences', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('falls back to the documented defaults when nothing is stored', async () => {
    const { useStore } = await import('./useStore')
    expect(useStore.getState().searchMode).toBe('name')
    expect(useStore.getState().searchSort).toBe('rank')
    expect(useStore.getState().searchOrder).toBe('asc')
    expect(useStore.getState().customsSort).toBe('recent')
    expect(useStore.getState().customsOrder).toBe('desc')
  })

  it('starts from what was chosen last time', async () => {
    localStorage.setItem('impeccable:search-mode', 'series')
    localStorage.setItem('impeccable:search-sort', 'alphabet')
    localStorage.setItem('impeccable:search-order', 'desc')
    localStorage.setItem('impeccable:customs-sort', 'count')
    localStorage.setItem('impeccable:customs-order', 'asc')
    const { useStore } = await import('./useStore')
    expect(useStore.getState().searchMode).toBe('series')
    expect(useStore.getState().searchSort).toBe('alphabet')
    expect(useStore.getState().searchOrder).toBe('desc')
    expect(useStore.getState().customsSort).toBe('count')
    expect(useStore.getState().customsOrder).toBe('asc')
  })

  it('writes each choice the moment it is made', async () => {
    const { useStore } = await import('./useStore')
    useStore.getState().setSearchMode('series')
    useStore.getState().setSearchSort('alphabet')
    useStore.getState().setSearchOrder('desc')
    useStore.getState().setCustomsSort('count')
    useStore.getState().setCustomsOrder('asc')
    expect(localStorage.getItem('impeccable:search-mode')).toBe('series')
    expect(localStorage.getItem('impeccable:search-sort')).toBe('alphabet')
    expect(localStorage.getItem('impeccable:search-order')).toBe('desc')
    expect(localStorage.getItem('impeccable:customs-sort')).toBe('count')
    expect(localStorage.getItem('impeccable:customs-order')).toBe('asc')
  })
})

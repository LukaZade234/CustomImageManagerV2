import { beforeEach, describe, expect, it } from 'vitest'
import {
  applyTheme,
  LEGACY_STORAGE_KEY,
  nextTheme,
  persistTheme,
  readStoredTheme,
  THEME_STORAGE_KEY,
  THEMES,
} from './theme'

beforeEach(() => {
  localStorage.clear()
  document.documentElement.removeAttribute('data-theme')
})

describe('readStoredTheme', () => {
  it('defaults to system when nothing is stored', () => {
    expect(readStoredTheme()).toBe('system')
  })

  it.each(THEMES)('round-trips %s', (theme) => {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
    expect(readStoredTheme()).toBe(theme)
  })

  it('ignores an unrecognised stored value', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'solarized')
    expect(readStoredTheme()).toBe('system')
  })

  it('migrates the legacy darkMode boolean so preferences survive the rewrite', () => {
    localStorage.setItem(LEGACY_STORAGE_KEY, 'true')
    expect(readStoredTheme()).toBe('dark')
    localStorage.setItem(LEGACY_STORAGE_KEY, 'false')
    expect(readStoredTheme()).toBe('light')
  })

  it('prefers the new key over the legacy one', () => {
    localStorage.setItem(THEME_STORAGE_KEY, 'light')
    localStorage.setItem(LEGACY_STORAGE_KEY, 'true')
    expect(readStoredTheme()).toBe('light')
  })
})

describe('applyTheme', () => {
  it('removes the attribute for system, so CSS falls through to prefers-color-scheme', () => {
    document.documentElement.setAttribute('data-theme', 'dark')
    applyTheme('system')
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false)
  })

  it.each(['light', 'dark'])('sets data-theme=%s for an explicit choice', (theme) => {
    applyTheme(theme)
    expect(document.documentElement.getAttribute('data-theme')).toBe(theme)
  })
})

describe('persistTheme', () => {
  it('stores the choice and clears the legacy key', () => {
    localStorage.setItem(LEGACY_STORAGE_KEY, 'true')
    persistTheme('light')
    expect(localStorage.getItem(THEME_STORAGE_KEY)).toBe('light')
    expect(localStorage.getItem(LEGACY_STORAGE_KEY)).toBeNull()
  })
})

describe('nextTheme', () => {
  it('cycles system -> light -> dark -> system', () => {
    expect(nextTheme('system')).toBe('light')
    expect(nextTheme('light')).toBe('dark')
    expect(nextTheme('dark')).toBe('system')
  })
})

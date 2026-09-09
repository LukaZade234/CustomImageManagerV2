/**
 * Theme is three-state: 'system' (the default) follows prefers-color-scheme,
 * while 'light' and 'dark' are explicit overrides that win in both directions.
 *
 * The DOM contract is a `data-theme` attribute on <html>, present only for an
 * explicit choice. tokens.css keys off its absence for the system case, so
 * "no attribute" must mean "follow the OS" — never write data-theme="system".
 */

export const THEME_STORAGE_KEY = 'theme'
/** Pre-token key: a boolean that only ever expressed dark-or-light. */
export const LEGACY_STORAGE_KEY = 'darkMode'
export const THEMES = ['system', 'light', 'dark']

export function readStoredTheme() {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY)
    if (THEMES.includes(stored)) return stored
    // Migrate existing visitors so nobody's preference silently resets.
    const legacy = localStorage.getItem(LEGACY_STORAGE_KEY)
    if (legacy === 'true') return 'dark'
    if (legacy === 'false') return 'light'
  } catch (_) {
    /* private mode / blocked storage */
  }
  return 'system'
}

export function applyTheme(theme) {
  if (typeof document === 'undefined') return
  const root = document.documentElement
  if (theme === 'system') root.removeAttribute('data-theme')
  else root.setAttribute('data-theme', theme)
}

export function persistTheme(theme) {
  try {
    localStorage.setItem(THEME_STORAGE_KEY, theme)
    localStorage.removeItem(LEGACY_STORAGE_KEY)
  } catch (_) {
    /* private mode / blocked storage */
  }
}

export function nextTheme(theme) {
  const i = THEMES.indexOf(theme)
  return THEMES[(i + 1) % THEMES.length]
}

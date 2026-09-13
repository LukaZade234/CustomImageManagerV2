import { useEffect } from 'react'

/**
 * Publishes a character's derived theme to `<html>` as the eight `--char-*`
 * custom properties tokens.css's "Per-character accent" block reads, and
 * toggles the class that activates it.
 *
 * Lives on `<html>` rather than on the page's own root element because the
 * point is reach: the navbar and its buttons sit outside `.character-page`
 * entirely, and custom properties only cascade to descendants.
 *
 * Removing the class and the properties on cleanup matters as much as setting
 * them: this runs again on every character-page mount, but the class must not
 * survive a navigation to a page that never calls this hook at all — the
 * profile page, the home page, the character that comes right after one with
 * no confident colour.
 */
export function useApplyCharacterTheme(theme) {
  useEffect(() => {
    if (!theme) return undefined

    const root = document.documentElement
    root.classList.add('has-character-theme')
    const entries = {
      '--char-accent': theme.light.accent,
      '--char-accent-hover': theme.light.hover,
      '--char-accent-subtle': theme.light.subtle,
      '--char-accent-fg': theme.light.fg,
      '--char-accent-dark': theme.dark.accent,
      '--char-accent-hover-dark': theme.dark.hover,
      '--char-accent-subtle-dark': theme.dark.subtle,
      '--char-accent-fg-dark': theme.dark.fg,
    }
    for (const [name, value] of Object.entries(entries)) {
      root.style.setProperty(name, value)
    }

    return () => {
      root.classList.remove('has-character-theme')
      for (const name of Object.keys(entries)) {
        root.style.removeProperty(name)
      }
    }
  }, [theme])
}

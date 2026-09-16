/**
 * The route-level code-splitting boundary.
 *
 * The whole app used to be one bundle, so every anonymous visitor downloaded the
 * moderation console and the profile subtree they cannot open. That is fixed by
 * loading those routes on demand — and the two easy ways to lose the fix again
 * are to statically import a heavy page, or to move the moderator guard inside
 * the lazy subtree so a non-moderator downloads the console before being
 * redirected. Both are invisible at runtime, so they are pinned here.
 */
import { readFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const source = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'App.jsx'), 'utf8')

const staticallyImported = (specifier) =>
  new RegExp(`^import\\s+\\w+\\s+from\\s+'${specifier}'`, 'm').test(source)

const lazilyImported = (specifier) => source.includes(`lazy(() => import('${specifier}'))`)

describe('App code splitting', () => {
  it('keeps the landing page and the shared chrome eager', () => {
    for (const specifier of [
      './pages/HomePage',
      './components/Navbar',
      './components/RequireModerator',
      './components/RestrictionBanner',
      './components/Toast',
    ]) {
      expect(staticallyImported(specifier), specifier).toBe(true)
    }
  })

  it('loads every heavy route on demand', () => {
    for (const specifier of [
      './pages/AddPage',
      './pages/CharacterPage',
      './pages/CustomsPage',
      './pages/NotificationsPage',
      './pages/SearchResultsPage',
      './pages/profile/ProfileLayout',
      './pages/moderation/DuplicatesPage',
      './pages/moderation/ModerationLayout',
      './pages/moderation/ModerationPage',
      './pages/moderation/ReportsPage',
    ]) {
      expect(lazilyImported(specifier), specifier).toBe(true)
    }
  })

  it('never statically imports a moderation or profile page', () => {
    expect(source).not.toMatch(/^import\s+\w+\s+from\s+'\.\/pages\/(moderation|profile)\//m)
  })

  it('mounts the moderator guard outside the moderation chunk', () => {
    // Non-moderators must be turned away without the console being fetched.
    expect(source).toMatch(/<RequireModerator>\s*<ModerationLayout\s*\/>\s*<\/RequireModerator>/)
  })
})

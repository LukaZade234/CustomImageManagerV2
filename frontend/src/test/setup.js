import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

/**
 * jsdom has no layout, so it has no `matchMedia` either.
 *
 * Components that branch on viewport width — the navbar's folding links, the
 * gallery's column layout — would otherwise throw on first render. This stands
 * in for it and reports every query as not matching, which is the wide layout:
 * one shape for tests to assert against rather than whichever one the harness
 * happens to imply. A test that wants the narrow one overrides this.
 */
if (!window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query) => ({
    media: query,
    matches: false,
    onchange: null,
    addEventListener: () => {},
    removeEventListener: () => {},
    addListener: () => {},
    removeListener: () => {},
    dispatchEvent: () => false,
  }))
}

/**
 * jsdom does not scroll. Its `window.scrollTo` exists but reports "not
 * implemented" to the console, which a component that scrolls to the top on a
 * page change would repeat on every test that paginates. A no-op keeps the
 * output readable; a test that cares spies on it.
 */
window.scrollTo = () => {}

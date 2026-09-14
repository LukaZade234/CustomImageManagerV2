import { create } from 'zustand'
import { applyTheme, nextTheme, persistTheme, readStoredTheme, THEMES } from '../theme'
import {
  CUSTOMS_ORDER_KEY,
  CUSTOMS_SORT_KEY,
  readStored,
  SEARCH_MODE_KEY,
  SEARCH_ORDER_KEY,
  SEARCH_SORT_KEY,
  writeStored,
} from '../utils/storedSetting'

/**
 * Client state only.
 *
 * Server state — the gallery, the catalog lookups, saved, stats and `me` — lives
 * in react-query (see `queries/`), which owns its cache, retry and invalidation.
 * What stays here is what the browser owns: theme, toasts, the current
 * character, and the search/sort choices remembered across visits.
 */

/** The remembered sort may predate the current option set; fall back to rank. */
function readStoredSort() {
  const value = readStored(SEARCH_SORT_KEY, 'rank')
  return ['rank', 'alphabet', 'count'].includes(value) ? value : 'rank'
}

/** Customs once stored a composite key ("count_desc"); keep only the field now. */
function readStoredCustomsSort() {
  const value = readStored(CUSTOMS_SORT_KEY, 'recent')
  return ['recent', 'rank', 'alphabet', 'count'].includes(value) ? value : 'recent'
}

export const useStore = create((set, get) => ({
  currentCharacter: null,
  theme: readStoredTheme(),

  setTheme: (theme) => {
    if (!THEMES.includes(theme)) return
    set({ theme })
    applyTheme(theme)
    persistTheme(theme)
  },
  cycleTheme: () => {
    get().setTheme(nextTheme(get().theme))
  },

  setCurrentCharacter: (char) => set({ currentCharacter: char }),
  clearCurrentCharacter: () => set({ currentCharacter: null }),

  searchQuery: '',
  setSearchQuery: (q) => set({ searchQuery: q || '' }),
  // Search-by field and sort are remembered across visits, because they are
  // choices rather than state: coming back to the search you last used should
  // not mean re-picking "Series". Shared between the navbar's search and Browse
  // Customs, which ask the same question. `customsSort` is separate because its
  // options are a different set.
  searchMode: readStored(SEARCH_MODE_KEY, 'name'),
  searchSort: readStoredSort(),
  // The default sort is rank, and rank 1 is the top rank, so descending is what
  // reads best-first (the search hook swaps it for the literal server order).
  searchOrder: readStored(SEARCH_ORDER_KEY, 'desc'),
  customsSort: readStoredCustomsSort(),
  customsOrder: readStored(CUSTOMS_ORDER_KEY, 'desc'),
  setSearchMode: (m) => {
    writeStored(SEARCH_MODE_KEY, m)
    set({ searchMode: m })
  },
  setSearchSort: (s) => {
    writeStored(SEARCH_SORT_KEY, s)
    set({ searchSort: s })
  },
  setSearchOrder: (o) => {
    writeStored(SEARCH_ORDER_KEY, o)
    set({ searchOrder: o })
  },
  setCustomsSort: (s) => {
    writeStored(CUSTOMS_SORT_KEY, s)
    set({ customsSort: s })
  },
  setCustomsOrder: (o) => {
    writeStored(CUSTOMS_ORDER_KEY, o)
    set({ customsOrder: o })
  },

  toasts: [],
  /**
   * @param {string} msg
   * @param {'success'|'error'|'info'} [type]
   * @param {{ onUndo?: () => void | Promise<void>, undoLabel?: string, duration?: number }} [options]
   *   — when `onUndo` is set, default duration is longer so the user can tap Undo.
   */
  addToast: (msg, type = 'info', options = {}) => {
    const id = Date.now() + Math.random()
    const { onUndo, undoLabel = 'Undo', duration } = options
    const ms = typeof duration === 'number' ? duration : onUndo ? 8000 : 4000
    set((s) => ({ toasts: [...s.toasts, { id, msg, type, onUndo, undoLabel }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), ms)
  },
  removeToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

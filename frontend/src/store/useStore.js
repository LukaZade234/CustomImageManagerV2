import { create } from 'zustand'
import { apiClient } from '../api'
import { applyTheme, nextTheme, persistTheme, readStoredTheme, THEMES } from '../theme'

/** Transient browser / gateway failures worth retrying (not 4xx validation). */
function shouldRetryFetchError(e) {
  if (e instanceof TypeError) return true
  const m = e?.message || ''
  if (m.startsWith('Network error:')) return true
  if (/could not complete the request/i.test(m)) return true
  if (/Gateway|502|503|504/i.test(m)) return true
  return false
}

export const useStore = create((set, get) => ({
  characters: [],
  savedCharacters: [],
  // Per-character rows: id, url, owner, is_mine, hidden. Loaded on demand for
  // the character page only. There is deliberately no library-wide image map any
  // more -- Home and Customs ask the server for what they need.
  characterImages: {},
  stats: null,
  me: null,
  currentCharacter: null,
  loading: false,
  error: null,
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

  loadCharacters: async () => {
    set({ loading: true, error: null })
    try {
      const data = await apiClient.getCharacters()
      set({ characters: data || [], loading: false })
      return data
    } catch (e) {
      set({ error: e.message, loading: false })
      return []
    }
  },

  loadSaved: async () => {
    try {
      // Already ordered most-recently-updated first by the server, which knows
      // the timestamps without shipping a map of all ~700 characters.
      set({ savedCharacters: (await apiClient.getSaved()) || [] })
    } catch {
      set({ savedCharacters: [] })
    }
  },

  /** Two integers for the landing page, in place of the whole library. */
  loadStats: async () => {
    try {
      set({ stats: await apiClient.getStats() })
    } catch {
      /* keep whatever we had; a stale count beats an empty page */
    }
  },

  /** Who the server thinks we are. Handle, role, sign-in state — never the id. */
  loadMe: async () => {
    try {
      set({ me: await apiClient.getMe() })
    } catch {
      /* identity is best-effort; the page works without knowing the handle */
    }
  },

  /** One character’s images from GET /api/custom-image/<name>, with ownership. */
  loadCustomImagesForCharacter: async (characterName) => {
    if (!characterName) return
    const maxAttempts = 3
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const rows = await apiClient.getCustomImagesForChar(characterName)
        const list = Array.isArray(rows) ? rows : []
        set((s) => ({ characterImages: { ...s.characterImages, [characterName]: list } }))
        return
      } catch (e) {
        if (!shouldRetryFetchError(e) || attempt === maxAttempts - 1) break
        await new Promise((r) => setTimeout(r, 400 * 2 ** attempt + Math.random() * 200))
      }
    }
    /* keep previous slice for this character */
  },

  /**
   * Refresh a character after a successful upload or import.
   *
   * Refetches rather than appending the URLs it was handed: the rows need real
   * ids from the server before Hide or Report can act on them, and inventing
   * placeholder entries would make those actions fail on exactly the images
   * someone just added.
   */
  appendCustomImageUrls: async (characterName, urls) => {
    if (!characterName || !urls?.length) return
    await get().loadCustomImagesForCharacter(characterName)
  },

  /** After a server-side rename, move the character's cached rows to the new key. */
  renameCustomCharacterData: (oldName, newName) => {
    if (!oldName || !newName || oldName === newName) return
    set((s) => {
      const characterImages = { ...s.characterImages }
      if (Object.hasOwn(characterImages, oldName)) {
        characterImages[newName] = characterImages[oldName]
        delete characterImages[oldName]
      }
      return { characterImages }
    })
  },

  saveCharacter: async (char) => {
    await apiClient.saveCharacter(char)
    await get().loadSaved()
  },

  removeSaved: async (name) => {
    await apiClient.removeSaved(name)
    await get().loadSaved()
  },

  setCurrentCharacter: (char) => set({ currentCharacter: char }),
  clearCurrentCharacter: () => set({ currentCharacter: null }),

  searchQuery: '',
  setSearchQuery: (q) => set({ searchQuery: q || '' }),
  searchMode: 'name',
  searchSort: 'rank',
  setSearchMode: (m) => set({ searchMode: m }),
  setSearchSort: (s) => set({ searchSort: s }),

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

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
  lastUpdated: {},
  customImages: {},
  // customImages holds the URL-only map from /custom_images.json, which Home and
  // Customs use for counts and previews. characterImages holds the richer
  // per-character rows -- id, owner, is_mine, hidden -- that only the character
  // page needs. Keeping them apart avoids one map with two shapes in it.
  characterImages: {},
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
      const [saved, lastUpd] = await Promise.all([apiClient.getSaved(), apiClient.getLastUpdated()])
      set({ savedCharacters: saved || [], lastUpdated: lastUpd || {} })
      const sorted = [...(saved || [])].sort(
        (a, b) => (lastUpd[b.name] || 0) - (lastUpd[a.name] || 0),
      )
      set({ savedCharacters: sorted })
    } catch {
      set({ savedCharacters: [] })
    }
  },

  /** Full map — used by Home / Customs (stats, browse all). */
  loadCustomImages: async () => {
    const maxAttempts = 3
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const data = await apiClient.getCustomImages()
        set({ customImages: data || {} })
        try {
          const lastUpd = await apiClient.getLastUpdated()
          if (lastUpd && typeof lastUpd === 'object') set({ lastUpdated: lastUpd })
        } catch {
          /* keep existing lastUpdated */
        }
        return
      } catch (e) {
        if (!shouldRetryFetchError(e) || attempt === maxAttempts - 1) break
        await new Promise((r) => setTimeout(r, 400 * 2 ** attempt + Math.random() * 200))
      }
    }
    /* Keep previous customImages — clearing on a failed refresh hid successful uploads and worsened batch UX. */
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
        set((s) => ({
          characterImages: { ...s.characterImages, [characterName]: list },
          // Keep the bulk map in step so Home and Customs counts do not go
          // stale after a removal or restore on this page.
          customImages: { ...s.customImages, [characterName]: list.map((row) => row.url) },
        }))
        try {
          const lastUpd = await apiClient.getLastUpdated()
          if (lastUpd && typeof lastUpd === 'object') set({ lastUpdated: lastUpd })
        } catch {
          /* keep */
        }
        return
      } catch (e) {
        if (!shouldRetryFetchError(e) || attempt === maxAttempts - 1) break
        await new Promise((r) => setTimeout(r, 400 * 2 ** attempt + Math.random() * 200))
      }
    }
    /* keep previous slice for this character */
  },

  /** Append ImgChest URLs after a successful upload/import (server already saved). */
  appendCustomImageUrls: async (characterName, urls) => {
    if (!characterName || !urls?.length) return
    set((s) => ({
      customImages: {
        ...s.customImages,
        [characterName]: [...(s.customImages[characterName] || []), ...urls],
      },
    }))
    // The rows need real ids from the server before Hide or Report can act on
    // them, so refetch rather than inventing placeholder entries.
    get().loadCustomImagesForCharacter(characterName)
    try {
      const lastUpd = await apiClient.getLastUpdated()
      if (lastUpd && typeof lastUpd === 'object') set({ lastUpdated: lastUpd })
    } catch {
      /* keep */
    }
  },

  /**
   * After server-side rename of a character, move custom image URLs + timestamps to the new key
   * so Home/Customs stats do not double-count the old name.
   */
  renameCustomCharacterData: (oldName, newName) => {
    if (!oldName || !newName || oldName === newName) return
    set((s) => {
      const customImages = { ...s.customImages }
      if (Object.hasOwn(customImages, oldName)) {
        customImages[newName] = customImages[oldName]
        delete customImages[oldName]
      }
      const characterImages = { ...s.characterImages }
      if (Object.hasOwn(characterImages, oldName)) {
        characterImages[newName] = characterImages[oldName]
        delete characterImages[oldName]
      }
      const lastUpdated = { ...s.lastUpdated }
      if (Object.hasOwn(lastUpdated, oldName)) {
        lastUpdated[newName] = lastUpdated[oldName]
        delete lastUpdated[oldName]
      }
      return { customImages, characterImages, lastUpdated }
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

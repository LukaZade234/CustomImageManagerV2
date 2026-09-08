import { create } from 'zustand'
import { apiClient } from '../api'

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
  currentCharacter: null,
  loading: false,
  error: null,
  darkMode: typeof localStorage !== 'undefined' ? localStorage.getItem('darkMode') === 'true' : false,

  setDarkMode: (v) => {
    set({ darkMode: v })
    if (typeof document !== 'undefined') document.body.classList.toggle('dark-mode', v)
    if (typeof localStorage !== 'undefined') localStorage.setItem('darkMode', v ? 'true' : 'false')
  },
  toggleDarkMode: () => {
    const v = !get().darkMode
    get().setDarkMode(v)
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
      const [saved, lastUpd] = await Promise.all([
        apiClient.getSaved(),
        apiClient.getLastUpdated(),
      ])
      set({ savedCharacters: saved || [], lastUpdated: lastUpd || {} })
      const sorted = [...(saved || [])].sort((a, b) => (lastUpd[b.name] || 0) - (lastUpd[a.name] || 0))
      set({ savedCharacters: sorted })
    } catch (e) {
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

  /** One character’s URLs from GET /api/custom-image/<name> — merges into the map without loading everyone. */
  loadCustomImagesForCharacter: async (characterName) => {
    if (!characterName) return
    const maxAttempts = 3
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const urls = await apiClient.getCustomImagesForChar(characterName)
        const list = Array.isArray(urls) ? urls : []
        set((s) => ({
          customImages: { ...s.customImages, [characterName]: list },
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
      if (Object.prototype.hasOwnProperty.call(customImages, oldName)) {
        customImages[newName] = customImages[oldName]
        delete customImages[oldName]
      }
      const lastUpdated = { ...s.lastUpdated }
      if (Object.prototype.hasOwnProperty.call(lastUpdated, oldName)) {
        lastUpdated[newName] = lastUpdated[oldName]
        delete lastUpdated[oldName]
      }
      return { customImages, lastUpdated }
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

import { API_BASE, CREDENTIALS, imageUrl } from './config'
import { backoffDelay, isTransientError } from './utils/retry'

/** @param {Response} res @param {string} text @param {Record<string, unknown>} parsed */
function messageFromFailedResponse(res, text, parsed) {
  const base =
    typeof parsed?.error === 'string'
      ? parsed.error
      : typeof parsed?.message === 'string'
        ? parsed.message
        : ''
  const rawDetails = Array.isArray(parsed?.details)
    ? parsed.details.filter((d) => typeof d === 'string' && d.trim())
    : []
  const extraDetails = rawDetails.filter((d) => d !== base)
  const details = extraDetails.length ? ` — ${extraDetails.join('; ')}` : ''
  if (base) return base + details

  const raw = (text || '').trim().replace(/\s+/g, ' ')
  if (raw.startsWith('<') || !raw) {
    if (res.status === 502 || res.status === 503 || res.status === 504) {
      return `Gateway or upstream error (HTTP ${res.status}). Often a short overload or timeout between your browser and the app — try again in a moment.`
    }
    return `HTTP ${res.status} ${res.statusText || ''}. The server did not return a readable error (often HTML from a proxy). Check app logs or retry.`.trim()
  }
  const cap = 200000
  if (raw.length > cap) {
    return `HTTP ${res.status}: ${raw.slice(0, cap)}\n\n(Error response was ${raw.length} characters; showing first ${cap}.)`
  }
  return `HTTP ${res.status}: ${raw}`
}

function toNetworkError(err) {
  const m = err?.message || ''
  if (
    err instanceof TypeError &&
    (m === 'Failed to fetch' || m === 'Load failed' || /fetch/i.test(m))
  ) {
    return new Error(
      'Network error: the browser could not complete the request. Common causes: lost connection, the app restarting, or a timeout. Try again in a moment.',
    )
  }
  return err
}

/** Re-exported so existing imports keep working; the logic lives in config.js. */
const getImageUrl = imageUrl

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, { ...options, credentials: CREDENTIALS })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || err.message || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

export const apiClient = {
  getSaved: () => api('/api/saved'),
  getStats: () => api('/api/stats'),
  listCustoms: ({ page = 1, perPage = 20, q = '', by = 'name', sort = 'recent' } = {}) => {
    const params = new URLSearchParams({ page, per_page: perPage, by, sort })
    if (q) params.set('q', q)
    return api(`/api/customs?${params}`)
  },
  suggestCharacters: (q = '', limit = 10, series = '', pools = []) => {
    const params = new URLSearchParams({ q, limit: String(limit) })
    if (series) params.set('series', series)
    if (pools.length) params.set('pool', pools.join(','))
    return api(`/api/catalog/characters?${params}`)
  },
  suggestSeries: (q = '', limit = 20) =>
    api(`/api/catalog/series?q=${encodeURIComponent(q)}&limit=${limit}`),
  /**
   * One page of a catalog search. Returns `{ items, total }`; each item carries
   * `in_library`, so a catalog-only result can be offered for adding.
   */
  searchCharacters: ({
    q = '',
    by = 'name',
    sort = 'rank',
    order = 'asc',
    page = 1,
    perPage = 60,
  } = {}) => {
    const params = new URLSearchParams({
      q,
      by,
      sort,
      order,
      page: String(page),
      per_page: String(perPage),
    })
    return api(`/api/catalog/search?${params}`)
  },
  findCatalogCharacter: (name) => api(`/api/catalog/character?name=${encodeURIComponent(name)}`),
  catalogAddCharacter: (name) =>
    api('/api/catalog/add-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    }),
  saveCharacter: (data) =>
    api('/api/saved', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  removeSaved: (name) => api(`/api/saved/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  getCustomImagesForChar: (name) => api(`/api/custom-image/${encodeURIComponent(name)}`),
  addCustomImage: async (formData) => {
    const url = `${API_BASE}/api/custom-image`
    const maxAttempts = 4

    const attemptOnce = () =>
      fetch(url, { method: 'POST', body: formData, credentials: CREDENTIALS })
        .catch((e) => {
          throw toNetworkError(e)
        })
        .then(async (r) => {
          const text = await r.text()
          let j = {}
          try {
            j = text ? JSON.parse(text) : {}
          } catch {
            j = {}
          }
          if (!r.ok) {
            throw new Error(messageFromFailedResponse(r, text, j))
          }
          if (Array.isArray(j.errors) && j.errors.length > 0) {
            return { ...j, _partialErrors: j.errors }
          }
          return j
        })

    let lastErr
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        return await attemptOnce()
      } catch (e) {
        lastErr = e
        if (!isTransientError(e) || attempt === maxAttempts - 1) throw e
        await new Promise((resolve) => setTimeout(resolve, backoffDelay(attempt, 450)))
      }
    }
    throw lastErr
  },
  deleteCustomImage: (charName, imageUrl) =>
    api('/api/delete-custom-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_name: charName, image_url: imageUrl }),
    }),
  deleteCustomImages: (charName, imageUrls) =>
    api('/api/delete-custom-images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_name: charName, image_urls: imageUrls }),
    }),
  hideImages: (imageIds) =>
    api('/api/hide-images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_ids: imageIds }),
    }),
  unhideImages: (imageIds) =>
    api('/api/unhide-images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_ids: imageIds }),
    }),
  restoreImages: (charName, imageUrls) =>
    api('/api/restore-images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_name: charName, image_urls: imageUrls }),
    }),
  getRemovedImages: (charName) => api(`/api/removed/${encodeURIComponent(charName)}`),
  reportImage: (imageId, reason) =>
    api('/api/report-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_id: imageId, reason }),
    }),
  /**
   * Take logging drives nothing, so it must never surface an error or block the
   * action it accompanies. Failures are swallowed deliberately.
   */
  recordTakes: (imageIds, kind) =>
    api('/api/takes', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ image_ids: imageIds, kind }),
    }).catch(() => null),
  getMe: () => api('/api/me'),
  logout: () => api('/api/auth/logout', { method: 'POST' }),

  /* The profile page. Ownership is always recorded; these two only change what
     other people are shown, which is why they can be flipped back. */
  updateSettings: (settings) =>
    api('/api/me/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(settings),
    }),
  getMyHidden: () => api('/api/me/hidden'),
  getMyHistory: () => api('/api/me/history'),
  /* Explicit, so it fires when a page is actually shown rather than whenever
     something speculatively fetches. Failure is ignored: a view that went
     unrecorded is not worth telling anyone about. */
  recordView: (name) =>
    api(`/api/characters/${encodeURIComponent(name)}/view`, { method: 'POST' }).catch(() => null),
  getMyRemoved: () => api('/api/me/removed'),
  getMyContributions: () => api('/api/me/contributions'),
  importCustomImagesFromUrls: (characterName, urls) =>
    fetch(`${API_BASE}/api/import-custom-images-from-urls`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: CREDENTIALS,
      body: JSON.stringify({ character_name: characterName, urls }),
    })
      .catch((e) => {
        throw toNetworkError(e)
      })
      .then(async (r) => {
        const text = await r.text()
        let j = {}
        try {
          j = text ? JSON.parse(text) : {}
        } catch {
          j = {}
        }
        if (!r.ok) {
          throw new Error(messageFromFailedResponse(r, text, j))
        }
        if (Array.isArray(j.errors) && j.errors.length > 0) {
          return { ...j, _partialErrors: j.errors }
        }
        return j
      }),
  reorderCustomImages: (charName, newOrder) =>
    api('/api/reorder-custom-images', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_name: charName, new_order: newOrder }),
    }),
  setMainImage: (formData) =>
    fetch(`${API_BASE}/api/set-main-image`, {
      method: 'POST',
      body: formData,
      credentials: CREDENTIALS,
    }).then((r) =>
      r.ok
        ? r.json()
        : r.json().then((j) => {
            throw new Error(j.error || 'Upload failed')
          }),
    ),
  editCharacter: (data) =>
    api('/api/edit-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),
  addCharacter: (formData) =>
    fetch(`${API_BASE}/api/add-character`, {
      method: 'POST',
      body: formData,
      credentials: CREDENTIALS,
    }).then((r) =>
      r.ok
        ? r.json()
        : r.json().then((j) => {
            throw new Error(j.error || 'Failed')
          }),
    ),
  mudaeStatus: () => api('/api/mudae/status'),
  mudaeLookupCharacter: (name, add = false) =>
    api('/api/mudae/lookup-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, add }),
    }),
  mudaeSeriesExtract: (series) =>
    api('/api/mudae/series-extract', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ series }),
    }),
  mudaeSeriesExtractApply: (series, items) =>
    api('/api/mudae/series-extract/apply', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        series,
        items: items.map((c) => ({
          name: c.name,
          rank: c.rank,
          image_url: c.image_url,
        })),
      }),
    }),
  mudaeRefreshMainImage: (characterName) =>
    api('/api/mudae/refresh-main-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_name: characterName }),
    }),
}

export { getImageUrl }

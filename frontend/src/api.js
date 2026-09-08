const API_BASE = ''

/** @param {Response} res @param {string} text @param {Record<string, unknown>} parsed */
function messageFromFailedResponse(res, text, parsed) {
  const base = typeof parsed?.error === 'string' ? parsed.error : typeof parsed?.message === 'string' ? parsed.message : ''
  const rawDetails = Array.isArray(parsed?.details) ? parsed.details.filter((d) => typeof d === 'string' && d.trim()) : []
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
  if (err instanceof TypeError && (m === 'Failed to fetch' || m === 'Load failed' || /fetch/i.test(m))) {
    return new Error(
      'Network error: the browser could not complete the request. Common causes: lost connection, the app restarting, or a timeout. Try again in a moment.'
    )
  }
  return err
}

function getImageUrl(imagePath) {
  if (!imagePath) return ''
  if (imagePath.startsWith('http') || imagePath.startsWith('//')) return imagePath
  return `/character_images/${imagePath}`
}

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE}${path}`, { ...options, credentials: 'same-origin' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error || err.message || res.statusText)
  }
  if (res.status === 204) return null
  return res.json()
}

export const apiClient = {
  getCharacters: () => api('/api/characters'),
  getSaved: () => api('/api/saved'),
  getLastUpdated: () => api('/api/last-updated'),
  saveCharacter: (data) => api('/api/saved', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  removeSaved: (name) => api(`/api/saved/${encodeURIComponent(name)}`, { method: 'DELETE' }),
  getCustomImages: () => api('/custom_images.json'),
  getCustomImagesForChar: (name) => api(`/api/custom-image/${encodeURIComponent(name)}`),
  addCustomImage: async (formData) => {
    const url = `${API_BASE}/api/custom-image`
    const maxAttempts = 4

    const attemptOnce = () =>
      fetch(url, { method: 'POST', body: formData, credentials: 'same-origin' })
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
        const msg = e?.message || ''
        const transient =
          msg.startsWith('Network error:') || /could not complete the request/i.test(msg)
        if (!transient || attempt === maxAttempts - 1) throw e
        const delayMs = 450 * 2 ** attempt + Math.random() * 300
        await new Promise((resolve) => setTimeout(resolve, delayMs))
      }
    }
    throw lastErr
  },
  deleteCustomImage: (charName, imageUrl) => api('/api/delete-custom-image', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ character_name: charName, image_url: imageUrl }) }),
  deleteCustomImages: (charName, imageUrls) => api('/api/delete-custom-images', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ character_name: charName, image_urls: imageUrls }) }),
  importCustomImagesFromUrls: (characterName, urls) =>
    fetch(`${API_BASE}/api/import-custom-images-from-urls`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
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
  reorderCustomImages: (charName, newOrder) => api('/api/reorder-custom-images', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ character_name: charName, new_order: newOrder }) }),
  setMainImage: (formData) => fetch(`${API_BASE}/api/set-main-image`, { method: 'POST', body: formData, credentials: 'same-origin' }).then(r => r.ok ? r.json() : r.json().then(j => { throw new Error(j.error || 'Upload failed') })),
  editCharacter: (data) => api('/api/edit-character', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  addCharacter: (formData) => fetch(`${API_BASE}/api/add-character`, { method: 'POST', body: formData, credentials: 'same-origin' }).then(r => r.ok ? r.json() : r.json().then(j => { throw new Error(j.error || 'Failed') })),
  mudaeStatus: () => api('/api/mudae/status'),
  mudaeLookupCharacter: (name, add = false) =>
    api('/api/mudae/lookup-character', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, add }),
    }),
  mudaeLookupSeries: (series) =>
    api('/api/mudae/lookup-series', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ series }),
    }),
  mudaeAddSeries: (series) =>
    fetch(`${API_BASE}/api/mudae/add-series`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ series }),
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
        return j
      }),
  mudaeAddSeriesStream: async (series, handlers = {}) => {
    const res = await fetch(`${API_BASE}/api/mudae/add-series?stream=1`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
      credentials: 'same-origin',
      body: JSON.stringify({ series }),
    }).catch((e) => {
      throw toNetworkError(e)
    })

    if (!res.ok) {
      const text = await res.text()
      let j = {}
      try {
        j = text ? JSON.parse(text) : {}
      } catch {
        j = {}
      }
      throw new Error(messageFromFailedResponse(res, text, j))
    }

    const reader = res.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    let finalResult = null

    const dispatchBlock = (block) => {
      let event = 'message'
      let data = ''
      for (const line of block.split('\n')) {
        if (line.startsWith('event:')) event = line.slice(6).trim()
        else if (line.startsWith('data:')) data = line.slice(5).trim()
      }
      if (!data) return
      const parsed = JSON.parse(data)
      if (event === 'done') {
        finalResult = parsed
        return
      }
      if (event === 'error') {
        const err = new Error(parsed.error || 'Series import failed')
        if (parsed.type === 'candidates' && Array.isArray(parsed.candidate_matches)) {
          err.ambiguousSeries = true
          err.candidateMatches = parsed.candidate_matches
        }
        throw err
      }
      const fn = handlers[event]
      if (typeof fn === 'function') fn(parsed)
      else if (typeof handlers.onEvent === 'function') handlers.onEvent(event, parsed)
    }

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() || ''
      for (const block of parts) {
        if (block.trim()) dispatchBlock(block)
      }
    }
    if (buffer.trim()) dispatchBlock(buffer)
    return finalResult
  },
  mudaeCancelSeries: () =>
    api('/api/mudae/cancel-series', { method: 'POST' }),
  mudaeRefreshMainImage: (characterName) =>
    api('/api/mudae/refresh-main-image', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ character_name: characterName }),
    }),
}

export { getImageUrl }

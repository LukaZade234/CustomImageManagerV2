/**
 * Dragging images from web pages (Pinterest, etc.) provides URLs in text/uri-list or HTML,
 * not always File entries. Call on `drop` only — getData is restricted during dragover in some browsers.
 */

const HTTP_URL_RE = /^https?:\/\//i

/** Query params that are safe to ignore when comparing “same image” URLs (tracking / cache-bust noise). */
const TRACKING_QUERY_PARAMS = new Set([
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_content',
  'utm_term',
  'fbclid',
  'gclid',
  '_ga',
  'mc_eid',
  'igshid',
  'ref',
  'ref_src',
  'spm',
  'spm_id',
])

/**
 * Normalize URL for deduping (fragment + common tracking params). Same logical image often appears
 * with different query strings across text/uri-list vs HTML.
 */
export function canonicalImageUrlKey(href) {
  if (!href || typeof href !== 'string') return ''
  try {
    const u = new URL(href.trim())
    if (u.protocol !== 'http:' && u.protocol !== 'https:') return href.trim()
    u.hash = ''
    const toDelete = []
    u.searchParams.forEach((_, k) => {
      if (TRACKING_QUERY_PARAMS.has(k.toLowerCase())) toDelete.push(k)
    })
    toDelete.forEach((k) => u.searchParams.delete(k))
    const entries = [...u.searchParams.entries()]
    entries.sort((a, b) => a[0].localeCompare(b[0]) || String(a[1]).localeCompare(String(b[1])))
    u.search = ''
    for (const [k, v] of entries) {
      u.searchParams.append(k, v)
    }
    return u.href
  } catch {
    return href.trim().split('#')[0]
  }
}

/**
 * @param {string[]} urls
 * @returns {string[]} first occurrence per canonical key, order preserved
 */
export function dedupeImageUrls(urls) {
  const seen = new Set()
  const out = []
  for (const raw of urls) {
    if (!raw || typeof raw !== 'string') continue
    const key = canonicalImageUrlKey(raw)
    if (!key || seen.has(key)) continue
    seen.add(key)
    out.push(raw)
  }
  return out
}

function normalizeHttpUrl(s) {
  if (!s || typeof s !== 'string') return null
  const u = s.trim().split(/\s/)[0].split('#')[0]
  if (!HTTP_URL_RE.test(u)) return null
  try {
    const parsed = new URL(u)
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null
    return parsed.href
  } catch {
    return null
  }
}

/**
 * @param {DataTransfer} dt
 * @returns {string[]} unique image URLs
 */
export function extractImageUrlsFromDataTransfer(dt) {
  if (!dt) return []
  const out = new Set()

  try {
    const uriList = dt.getData('text/uri-list') || ''
    for (const line of uriList.split(/\r?\n/)) {
      const u = normalizeHttpUrl(line)
      if (u) out.add(u)
    }
  } catch {
    /* ignore */
  }

  try {
    const plain = dt.getData('text/plain')
    const u = normalizeHttpUrl(plain)
    if (u) out.add(u)
  } catch {
    /* ignore */
  }

  // Firefox / Windows: "URL\nTitle"
  try {
    const moz = dt.getData('text/x-moz-url')
    if (moz) {
      const firstLine = moz.split(/\r?\n/)[0]
      const u = normalizeHttpUrl(firstLine)
      if (u) out.add(u)
    }
  } catch {
    /* ignore */
  }

  try {
    const html = dt.getData('text/html')
    if (html && html.length > 0) {
      const doc = new DOMParser().parseFromString(html, 'text/html')
      doc.querySelectorAll('img[src]').forEach((img) => {
        const u = normalizeHttpUrl(img.getAttribute('src'))
        if (u) out.add(u)
      })
      doc.querySelectorAll('source[src]').forEach((el) => {
        const u = normalizeHttpUrl(el.getAttribute('src'))
        if (u) out.add(u)
      })
      doc.querySelectorAll('a[href]').forEach((a) => {
        const href = a.getAttribute('href')
        if (href && /\.(jpe?g|png|gif|webp|bmp|svg|avif)(\?|$)/i.test(href)) {
          const u = normalizeHttpUrl(href)
          if (u) out.add(u)
        }
      })
    }
  } catch {
    /* ignore */
  }

  return dedupeImageUrls([...out])
}

/** Types present during dragover (cannot rely on getData until drop). */
export function dataTransferHasWebImageDrag(dt) {
  if (!dt) return false
  try {
    const types = dt.types
    if (!types) return false
    if (typeof types.contains === 'function') {
      if (types.contains('text/uri-list') || types.contains('text/html')) return true
    }
    if (typeof types.includes === 'function') {
      if (types.includes('text/uri-list') || types.includes('text/html')) return true
    }
    const arr = Array.from(types)
    return arr.includes('text/uri-list') || arr.includes('text/html')
  } catch {
    return false
  }
}

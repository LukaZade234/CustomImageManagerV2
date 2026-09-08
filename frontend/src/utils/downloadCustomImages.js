import { getImageUrl } from '../api'

/** Safe filename from stored image key / path */
export function sanitizeFilenameFromUrl(url) {
  const path = (url || '').split('/').pop() || 'image.png'
  const cleaned = path.replace(/[^a-zA-Z0-9._-]/g, '_')
  return cleaned || 'image.png'
}

/** One unique filename per URL (handles duplicate basenames). */
export function uniqueFilenames(urls) {
  const used = new Set()
  const result = []
  for (const url of urls) {
    let base = sanitizeFilenameFromUrl(url)
    if (!used.has(base)) {
      used.add(base)
      result.push(base)
      continue
    }
    const dot = base.lastIndexOf('.')
    const stem = dot > 0 ? base.slice(0, dot) : base
    const ext = dot > 0 ? base.slice(dot) : ''
    let n = 2
    let candidate
    do {
      candidate = `${stem}_${n}${ext}`
      n++
    } while (used.has(candidate))
    used.add(candidate)
    result.push(candidate)
  }
  return result
}

/**
 * Remote images (e.g. ImgChest CDN) block cross-origin fetch in the browser (CORS).
 * Same-origin `/character_images/...` can be fetched directly.
 */
function isRemoteImageUrl(path) {
  if (!path) return false
  return /^https?:\/\//i.test(path) || path.startsWith('//')
}

function normalizeRemoteUrl(path) {
  if (path.startsWith('//')) return `https:${path}`
  return path
}

export async function fetchCustomImageBlob(storedUrl) {
  const path = getImageUrl(storedUrl)
  if (isRemoteImageUrl(path)) {
    const url = normalizeRemoteUrl(path)
    const res = await fetch('/api/download-image-proxy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({ url }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      throw new Error(err.error || `Could not load image (${res.status})`)
    }
    return res.blob()
  }
  const href = path.startsWith('/') ? path : `/${path}`
  const res = await fetch(new URL(href, window.location.origin).href, { credentials: 'same-origin' })
  if (!res.ok) throw new Error(`Could not load image (${res.status})`)
  return res.blob()
}

/**
 * Write images into a directory chosen via showDirectoryPicker (Chromium).
 * @param {string[]} urls — stored ImgChest URLs from the app
 * @param {FileSystemDirectoryHandle} dirHandle
 */
export async function writeCustomImagesToDirectory(urls, dirHandle) {
  const names = uniqueFilenames(urls)
  for (let i = 0; i < urls.length; i++) {
    const blob = await fetchCustomImageBlob(urls[i])
    const fileHandle = await dirHandle.getFileHandle(names[i], { create: true })
    const writable = await fileHandle.createWritable()
    await writable.write(blob)
    await writable.close()
  }
}

/**
 * Fallback: trigger one download per file (typically into the default Downloads folder).
 */
export async function downloadCustomImagesViaBrowser(urls) {
  const names = uniqueFilenames(urls)
  for (let i = 0; i < urls.length; i++) {
    const blob = await fetchCustomImageBlob(urls[i])
    const a = document.createElement('a')
    a.href = URL.createObjectURL(blob)
    a.download = names[i]
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(a.href)
    // Avoid blocking multiple downloads in some browsers
    await new Promise((r) => setTimeout(r, 120))
  }
}

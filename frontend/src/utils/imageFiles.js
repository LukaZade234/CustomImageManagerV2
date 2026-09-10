/**
 * Recognising and de-duplicating dropped image files.
 *
 * Both of these exist because browsers disagree about what they put in a
 * DataTransfer, and getting it wrong means a drop silently does nothing.
 */

/** Must match server MAX_FILE_SIZE in upload_imgchest.py (30 MiB) */
export const MAX_CUSTOM_IMAGE_BYTES = 30 * 1024 * 1024

const IMAGE_EXT_RE = /\.(jpe?g|png|gif|webp|bmp|svg|avif|heic|heif|ico)$/i

/** MIME image/* or an image extension — an OS drag often omits MIME on Linux. */
export function isImageFileLike(file) {
  if (!file) return false
  if (file.type?.startsWith('image/')) return true
  if (typeof file.name === 'string' && IMAGE_EXT_RE.test(file.name)) return true
  return false
}

/** Whether a DataTransfer carries files rather than, say, a dragged web image. */
export function dataTransferIsFileDrag(dt) {
  if (!dt) return false
  try {
    const { types, items } = dt
    // DOMStringList in Firefox and older WebKit has .contains but not .includes,
    // so the order of these checks matters.
    if (types) {
      if (typeof types.contains === 'function' && types.contains('Files')) return true
      if (typeof types.includes === 'function' && types.includes('Files')) return true
      const typeArr = Array.from(types)
      if (typeArr.includes('Files')) return true
      if (typeArr.includes('application/x-moz-file')) return true
    }
    if (items?.length) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') return true
      }
    }
    return false
  } catch {
    return false
  }
}

/** Some browsers list the same file more than once in a single drop. */
export function dedupeFilesByIdentity(fileList) {
  const seen = new Set()
  const out = []
  for (const f of fileList) {
    const key = `${f.name}\0${f.size}\0${f.lastModified}`
    if (seen.has(key)) continue
    seen.add(key)
    out.push(f)
  }
  return out
}

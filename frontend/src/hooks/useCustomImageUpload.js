import { useCallback, useRef, useState } from 'react'
import { apiClient } from '../api'
import { dedupeImageUrls, extractImageUrlsFromDataTransfer } from '../utils/dragImageUrls'
import { dedupeFilesByIdentity, isImageFileLike, MAX_CUSTOM_IMAGE_BYTES } from '../utils/imageFiles'

/**
 * Adding custom images to a character, from a file picker, a file drop, or an
 * image dragged in from another web page.
 *
 * All three routes share one lock, because they all end in the same place and a
 * second upload starting mid-flight would interleave progress reporting and
 * confuse the gallery refresh. The lock is a ref rather than state: it has to be
 * readable and writable synchronously inside an async loop, where a state update
 * would not have landed yet.
 *
 * Failures accumulate rather than aborting. A batch of twenty where three fail
 * should still add the seventeen, and the three are collected into one
 * copyable report instead of seventeen toasts scrolling past.
 */
export function useCustomImageUpload({ characterName, onUploaded, addToast, fileInputRef }) {
  const [progress, setProgress] = useState(null)
  const [errorReport, setErrorReport] = useState(null)
  const [dragOver, setDragOver] = useState(false)
  /** One upload at a time; see above for why this is a ref. */
  const busy = useRef(false)

  const runCustomUpload = async (fileList) => {
    const list = dedupeFilesByIdentity(Array.from(fileList)).filter((f) => isImageFileLike(f))
    if (!list.length) {
      addToast('No image files to upload', 'error')
      return
    }
    if (busy.current) {
      addToast('An upload is already in progress', 'info')
      return
    }
    busy.current = true
    const total = list.length
    setProgress({ phase: 'starting', current: 0, total })
    addToast(`Starting upload of ${total} image${total !== 1 ? 's' : ''}…`, 'info')

    const errors = []
    try {
      for (let i = 0; i < list.length; i++) {
        const file = list[i]
        setProgress({ phase: 'uploading', current: i + 1, total, fileName: file.name })
        if (file.size > MAX_CUSTOM_IMAGE_BYTES) {
          const msg = `File too large (max ${MAX_CUSTOM_IMAGE_BYTES / (1024 * 1024)}MB)`
          addToast(`Skipped ${i + 1}/${total} — ${file.name}: ${msg}`, 'error')
          errors.push({ name: file.name, message: msg })
          continue
        }
        try {
          const fd = new FormData()
          fd.append('character_name', characterName)
          fd.append('files', file)
          const res = await apiClient.addCustomImage(fd)
          if (Array.isArray(res.links) && res.links.length > 0) {
            await onUploaded(characterName, res.links)
          }
          // Server can return 200 with `errors` when a batch had partial failures (e.g. multi-file request)
          if (res && Array.isArray(res._partialErrors) && res._partialErrors.length) {
            res._partialErrors.forEach((msg) => {
              addToast(`Skipped: ${msg}`, 'error')
              errors.push({ name: file.name, message: msg })
            })
          }
        } catch (err) {
          const msg = err.message || 'Upload failed'
          addToast(`Failed ${i + 1}/${total} (${file.name}): ${msg}`, 'error')
          errors.push({ name: file.name, message: msg })
        }
      }

      const ok = total - errors.length
      if (ok === total) {
        addToast(`${ok} image${ok !== 1 ? 's' : ''} uploaded successfully.`, 'success')
      } else if (ok > 0) {
        addToast(
          `${ok} of ${total} image${ok !== 1 ? 's' : ''} uploaded. ${errors.length} failed — open the error panel to read and copy details.`,
          'error',
        )
      } else {
        addToast(`No images uploaded — open the error panel for full details.`, 'error')
      }
      if (errors.length > 0) {
        const detail = [
          `Some images were skipped or failed (${errors.length} of ${total}).`,
          '',
          'Per file:',
          '',
          ...errors.map((e) => (e.name ? `${e.name}\n  ${e.message}` : e.message)),
          '',
          'Tip: uploads to ImgChest are retried on the server; the browser also retries brief connection errors. New URLs are merged into the gallery without reloading the full library. If you see a network error, try again.',
        ].join('\n')
        setErrorReport(detail)
      }
    } catch (err) {
      addToast(`Upload stopped: ${err.message || 'Unknown error'}`, 'error')
    } finally {
      busy.current = false
      setProgress(null)
    }
  }

  const handleAddCustomImage = async (e) => {
    const files = e.target.files
    if (!files?.length) return
    await runCustomUpload(files)
    if (fileInputRef?.current) fileInputRef.current.value = ''
  }

  const runImportFromUrls = async (urls) => {
    const deduped = dedupeImageUrls(urls)
    if (!deduped.length) return
    if (busy.current) {
      addToast('An upload is already in progress', 'info')
      return
    }
    // Web drag often yields duplicate URLs for the same image; max 1 import per web drop only.
    const list = deduped.slice(0, 1)
    busy.current = true
    setProgress({ phase: 'uploading', current: 1, total: 1 })
    addToast(
      deduped.length > 1
        ? 'Importing one image from the web (extra URLs ignored)…'
        : 'Importing image from the web…',
      'info',
    )
    try {
      const res = await apiClient.importCustomImagesFromUrls(characterName, list)
      if (Array.isArray(res.links) && res.links.length > 0) {
        await onUploaded(characterName, res.links)
      }
      if (res && Array.isArray(res._partialErrors) && res._partialErrors.length) {
        res._partialErrors.forEach((msg) => addToast(`Skipped: ${msg}`, 'error'))
      }
      const n = (res && res.links && res.links.length) || 0
      if (n >= 1) {
        addToast('Image imported from the web.', 'success')
      } else {
        addToast('Could not import from that URL.', 'error')
      }
    } catch (err) {
      addToast(err.message || 'Import failed', 'error')
    } finally {
      busy.current = false
      setProgress(null)
    }
  }

  const handleCustomDrop = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragOver(false)

    const urls = extractImageUrlsFromDataTransfer(e.dataTransfer)
    const raw = e.dataTransfer.files
    const files = Array.from(raw || []).filter((f) => isImageFileLike(f))

    if (busy.current) {
      addToast('An upload is already in progress', 'info')
      return
    }

    if (files.length) {
      await runCustomUpload(files)
      return
    }
    if (urls.length) {
      await runImportFromUrls(urls)
      return
    }
    if (raw && raw.length > 0) {
      addToast('Drop image files only (PNG, JPEG, WebP, …)', 'info')
    }
  }

  /**
   * An OS file drag often omits `Files` from `types` until the drop itself, and
   * `dropEffect: none` cancels the drop event outright — so this always accepts.
   * Since reorder moved to pointer events, a drag arriving here can only have
   * come from outside, and there is nothing left to distinguish.
   */
  const handleCustomSectionDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
    setDragOver(true)
  }

  const handleCustomSectionDragLeave = (e) => {
    const next = e.relatedTarget
    if (next && e.currentTarget.contains(next)) return
    setDragOver(false)
  }

  return {
    progress,
    errorReport,
    dismissErrorReport: useCallback(() => setErrorReport(null), []),
    dragOver,
    onFileInputChange: handleAddCustomImage,
    onDrop: handleCustomDrop,
    onDragOver: handleCustomSectionDragOver,
    onDragLeave: handleCustomSectionDragLeave,
  }
}

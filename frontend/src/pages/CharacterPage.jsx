import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useStore } from '../store/useStore'
import { apiClient, getImageUrl } from '../api'
import ImageModal from '../components/ImageModal'
import UploadErrorDialog from '../components/UploadErrorDialog'
import AiCommandLimitDialog from '../components/AiCommandLimitDialog'
import {
  buildAiCommand,
  splitAiCommandForLimit,
  DISCORD_LIMIT_REGULAR,
  DISCORD_LIMIT_NITRO,
} from '../utils/aiCommandDiscord'
import { writeCustomImagesToDirectory, downloadCustomImagesViaBrowser } from '../utils/downloadCustomImages'
import { extractImageUrlsFromDataTransfer, dataTransferHasWebImageDrag, dedupeImageUrls } from '../utils/dragImageUrls'

/** Must match server MAX_FILE_SIZE in upload_imgchest.py (30 MiB) */
const MAX_CUSTOM_IMAGE_BYTES = 30 * 1024 * 1024

/** Mobile reorder: HTML5 DnD does not work with touch — long-press then drag */
const REORDER_LONG_PRESS_MS = 450
const REORDER_TOUCH_SLOP_PX = 14

const IMAGE_EXT_RE = /\.(jpe?g|png|gif|webp|bmp|svg|avif|heic|heif|ico)$/i

/** MIME image/* or empty type with image extension (OS drag often omits MIME on Linux). */
function isImageFileLike(file) {
  if (!file) return false
  if (file.type && file.type.startsWith('image/')) return true
  if (typeof file.name === 'string' && IMAGE_EXT_RE.test(file.name)) return true
  return false
}

function dataTransferIsFileDrag(dt) {
  if (!dt) return false
  try {
    const { types, items } = dt
    // DOMStringList (Firefox / older WebKit): has .contains, not .includes — check contains first
    if (types) {
      if (typeof types.contains === 'function' && types.contains('Files')) return true
      if (typeof types.includes === 'function' && types.includes('Files')) return true
      const typeArr = Array.from(types)
      if (typeArr.includes('Files')) return true
      if (typeArr.includes('application/x-moz-file')) return true
    }
    if (items && items.length) {
      for (let i = 0; i < items.length; i++) {
        if (items[i].kind === 'file') return true
      }
    }
    return false
  } catch {
    return false
  }
}

function adjustDropTarget(toIndex, pickedSet, len) {
  if (len <= 0) return 0
  let t = toIndex
  if (t < 0) t = 0
  if (t >= len) t = len - 1
  if (!pickedSet.has(t)) return t
  for (let i = t + 1; i < len; i++) if (!pickedSet.has(i)) return i
  for (let i = t - 1; i >= 0; i--) if (!pickedSet.has(i)) return i
  return 0
}

/** Move one contiguous group of indices to a drop target index (same visual order as `customs`). */
function moveGroupInArray(arr, fromIndices, toIndex) {
  const sorted = [...fromIndices].sort((a, b) => a - b)
  const pickedSet = new Set(sorted)
  const picked = sorted.map((i) => arr[i])
  let t = toIndex
  if (pickedSet.has(t)) {
    t = adjustDropTarget(t, pickedSet, arr.length)
  }
  if (t < 0) t = 0
  const without = arr.filter((_, i) => !pickedSet.has(i))
  let insertBefore = 0
  for (let i = 0; i < t && i < arr.length; i++) {
    if (!pickedSet.has(i)) insertBefore++
  }
  return [...without.slice(0, insertBefore), ...picked, ...without.slice(insertBefore)]
}

function ordersEqual(a, b) {
  if (a.length !== b.length) return false
  return a.every((u, i) => u === b[i])
}

/** Some browsers list the same file more than once in a single drop. */
function dedupeFilesByIdentity(fileList) {
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

export default function CharacterPage() {
  const { name } = useParams()
  const navigate = useNavigate()
  const characters = useStore((s) => s.characters)
  const savedCharacters = useStore((s) => s.savedCharacters)
  const customImages = useStore((s) => s.customImages)
  const loadCustomImagesForCharacter = useStore((s) => s.loadCustomImagesForCharacter)
  const appendCustomImageUrls = useStore((s) => s.appendCustomImageUrls)
  const loadCharacters = useStore((s) => s.loadCharacters)
  const loadSaved = useStore((s) => s.loadSaved)
  const renameCustomCharacterData = useStore((s) => s.renameCustomCharacterData)
  const saveCharacter = useStore((s) => s.saveCharacter)
  const removeSaved = useStore((s) => s.removeSaved)
  const addToast = useStore((s) => s.addToast)

  const char = characters.find((c) => c.name === name) || savedCharacters.find((c) => c.name === name)
  const customs = customImages[name] || []
  const isSaved = savedCharacters.some((s) => s.name === name)

  const [editMode, setEditMode] = useState(false)
  const [editName, setEditName] = useState('')
  const [editSeries, setEditSeries] = useState('')
  const [editRank, setEditRank] = useState('')
  const [mainImage, setMainImage] = useState('')
  const [loading, setLoading] = useState(false)
  const [mudaeMainBusy, setMudaeMainBusy] = useState(false)
  const [mudaeConfigured, setMudaeConfigured] = useState(false)
  const [aiMode, setAiMode] = useState(false)
  const [aiLimitDialog, setAiLimitDialog] = useState(null)
  const [deleteMode, setDeleteMode] = useState(false)
  const [downloadMode, setDownloadMode] = useState(false)
  const [reorderMode, setReorderMode] = useState(false)
  const [selectedUrls, setSelectedUrls] = useState([])
  const [modalOpen, setModalOpen] = useState(false)
  const [modalIndex, setModalIndex] = useState(0)
  const [dragOver, setDragOver] = useState(false)
  const [customDragOver, setCustomDragOver] = useState(false)
  const [customUploadProgress, setCustomUploadProgress] = useState(null)
  /** Full multi-line upload error for dismissible dialog (replaces window.alert). */
  const [uploadErrorDialog, setUploadErrorDialog] = useState(null)
  const customUploadLockRef = useRef(false)
  const mainInputRef = useRef(null)
  const customInputRef = useRef(null)
  const dragItemRef = useRef(null)
  const dragOverRef = useRef(null)
  const dragIndicesRef = useRef(null)
  /** Snapshot of custom image URLs when reorder session started (Cancel restores this order) */
  const reorderSessionBaselineRef = useRef(null)
  /** Drop target & dragged indices for reorder UI (refs alone don't re-render) */
  const [reorderDropTargetIndex, setReorderDropTargetIndex] = useState(null)
  const [reorderDragIndices, setReorderDragIndices] = useState(null)
  /** Last pointer Y during reorder drag — drives continuous edge auto-scroll */
  const reorderEdgePointerYRef = useRef(null)
  /** Touch long-press before drag: { timerId, index, startX, startY } */
  const reorderTouchPendingRef = useRef(null)
  /** Ignore one synthetic click after a touch-based reorder (avoids toggling selection) */
  const ignoreNextReorderItemClickRef = useRef(false)
  /** Stable cleanup for window-level touch listeners */
  const reorderTouchCleanupRef = useRef(null)
  /** Cancels in-flight long-press (window listeners + timer) */
  const reorderTouchCancelPendingRef = useRef(null)

  useEffect(() => {
    if (char) {
      setEditName(char.name)
      setEditSeries(char.series || '')
      setEditRank(char.rank || '')
      setMainImage(char.image || '')
    }
  }, [char])

  useEffect(() => {
    apiClient.mudaeStatus()
      .then((r) => setMudaeConfigured(!!r.configured))
      .catch(() => setMudaeConfigured(false))
  }, [])

  useEffect(() => {
    loadCustomImagesForCharacter(name)
  }, [name, loadCustomImagesForCharacter])

  useEffect(() => {
    if (!reorderMode) {
      if (typeof reorderTouchCleanupRef.current === 'function') {
        reorderTouchCleanupRef.current()
        reorderTouchCleanupRef.current = null
      }
      if (typeof reorderTouchCancelPendingRef.current === 'function') {
        reorderTouchCancelPendingRef.current()
        reorderTouchCancelPendingRef.current = null
      }
      const pending = reorderTouchPendingRef.current
      if (pending?.timerId) clearTimeout(pending.timerId)
      reorderTouchPendingRef.current = null
      document.body.classList.remove('reorder-touch-dragging')
      dragItemRef.current = null
      dragOverRef.current = null
      dragIndicesRef.current = null
      setReorderDropTargetIndex(null)
      setReorderDragIndices(null)
    }
  }, [reorderMode])

  /**
   * Continuous edge scroll while reorder-dragging: dragover only fires when the pointer moves,
   * so we run a rAF loop and read the last known Y — scrolling keeps going while the pointer
   * stays in the top/bottom bands.
   */
  useEffect(() => {
    if (!reorderDragIndices) return
    const edge = 100
    const maxStep = 28
    const minStep = 5
    let rafId = 0

    const onPointerMove = (e) => {
      if (typeof e.clientY === 'number') reorderEdgePointerYRef.current = e.clientY
    }

    const tick = () => {
      const y = reorderEdgePointerYRef.current
      if (y != null) {
        const h = window.innerHeight
        if (y < edge) {
          const d = edge - y
          const step = Math.round(Math.min(maxStep, Math.max(minStep, 4 + d * 0.22)))
          window.scrollBy(0, -step)
        } else if (y > h - edge) {
          const d = y - (h - edge)
          const step = Math.round(Math.min(maxStep, Math.max(minStep, 4 + d * 0.22)))
          window.scrollBy(0, step)
        }
      }
      rafId = requestAnimationFrame(tick)
    }

    reorderEdgePointerYRef.current = null
    document.addEventListener('dragover', onPointerMove, { passive: true })
    document.addEventListener('drag', onPointerMove, { passive: true })
    const onTouchMoveEdge = (e) => {
      const t = e.touches && e.touches[0]
      if (t) reorderEdgePointerYRef.current = t.clientY
    }
    document.addEventListener('touchmove', onTouchMoveEdge, { passive: true })
    rafId = requestAnimationFrame(tick)

    return () => {
      cancelAnimationFrame(rafId)
      document.removeEventListener('dragover', onPointerMove)
      document.removeEventListener('drag', onPointerMove)
      document.removeEventListener('touchmove', onTouchMoveEdge)
      reorderEdgePointerYRef.current = null
    }
  }, [reorderDragIndices])

  useEffect(() => {
    return () => {
      if (typeof reorderTouchCleanupRef.current === 'function') reorderTouchCleanupRef.current()
      if (typeof reorderTouchCancelPendingRef.current === 'function') reorderTouchCancelPendingRef.current()
      const p = reorderTouchPendingRef.current
      if (p?.timerId) clearTimeout(p.timerId)
      reorderTouchPendingRef.current = null
    }
  }, [])

  const resetModes = useCallback(() => {
    setAiMode(false)
    setDeleteMode(false)
    setDownloadMode(false)
    setReorderMode(false)
    setSelectedUrls([])
    setAiLimitDialog(null)
    reorderSessionBaselineRef.current = null
  }, [])

  const enterDownloadMode = useCallback(() => {
    setAiMode(false)
    setDeleteMode(false)
    setReorderMode(false)
    reorderSessionBaselineRef.current = null
    setSelectedUrls([])
    setDownloadMode(true)
  }, [])

  const enterReorderMode = useCallback(() => {
    setAiMode(false)
    setDeleteMode(false)
    setDownloadMode(false)
    setSelectedUrls([])
    reorderSessionBaselineRef.current = [...customs]
    setReorderMode(true)
  }, [customs])

  const cancelReorder = useCallback(async () => {
    const baseline = reorderSessionBaselineRef.current
    try {
      if (baseline) {
        await apiClient.reorderCustomImages(name, baseline)
        await loadCustomImagesForCharacter(name)
      }
      reorderSessionBaselineRef.current = null
      setReorderMode(false)
      setSelectedUrls([])
      setReorderDropTargetIndex(null)
      setReorderDragIndices(null)
      addToast('Order reverted to before you started reordering.', 'info')
    } catch (e) {
      addToast(e.message || 'Could not revert order', 'error')
    }
  }, [name, loadCustomImagesForCharacter, addToast])

  const doneReorder = useCallback(() => {
    reorderSessionBaselineRef.current = null
    setReorderMode(false)
    setSelectedUrls([])
    setReorderDropTargetIndex(null)
    setReorderDragIndices(null)
  }, [])

  const getIndicesToMove = useCallback(
    (startIndex) => {
      const indices = customs
        .map((u, i) => (selectedUrls.includes(u) ? i : -1))
        .filter((i) => i >= 0)
        .sort((a, b) => a - b)
      if (indices.length === 0) return [startIndex]
      if (indices.includes(startIndex)) return indices
      return [startIndex]
    },
    [customs, selectedUrls]
  )

  const beginReorderDrag = useCallback(
    (index) => {
      const indices = getIndicesToMove(index)
      dragIndicesRef.current = indices
      dragItemRef.current = index
      setReorderDragIndices(indices)
    },
    [getIndicesToMove]
  )

  const applyReorder = useCallback(
    (newOrder) => {
      apiClient
        .reorderCustomImages(name, newOrder)
        .then(() => {
          loadCustomImagesForCharacter(name)
          addToast('Order updated', 'success')
        })
        .catch((err) => addToast(err.message, 'error'))
    },
    [name, loadCustomImagesForCharacter, addToast]
  )

  if (!char) return <div className="loading">Character not found</div>

  const handleSaveEdit = async () => {
    setLoading(true)
    try {
      await apiClient.editCharacter({ original_name: name, new_name: editName, series: editSeries, rank: editRank })
      await loadCharacters()
      await loadSaved()
      if (name !== editName) {
        renameCustomCharacterData(name, editName)
      }
      addToast('Character updated', 'success')
      setEditMode(false)
      navigate(`/character/${encodeURIComponent(editName)}`, { replace: true })
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleToggleSave = async () => {
    try {
      if (isSaved) {
        await removeSaved(name)
        addToast('Removed from saved', 'success')
      } else {
        await saveCharacter(char)
        addToast('Saved character', 'success')
      }
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleMainImageChange = async (e) => {
    const file = e.target.files?.[0]
    if (!file) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('character_name', name)
    try {
      const res = await apiClient.setMainImage(fd)
      setMainImage(res.image_url)
      addToast('Main image updated', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleMainImageDrop = (e) => {
    e.preventDefault()
    setDragOver(false)
    const file = e.dataTransfer.files?.[0]
    if (!isImageFileLike(file)) return
    const fd = new FormData()
    fd.append('file', file)
    fd.append('character_name', name)
    apiClient.setMainImage(fd).then((res) => {
      setMainImage(res.image_url)
      addToast('Main image updated', 'success')
    }).catch((err) => addToast(err.message, 'error'))
  }

  const handleMudaeRefreshMain = async () => {
    if (!name || mudaeMainBusy) return
    setMudaeMainBusy(true)
    addToast('Fetching main image from Mudae…', 'info')
    try {
      const res = await apiClient.mudaeRefreshMainImage(name)
      setMainImage(res.image_url)
      await loadCharacters()
      addToast(res.message || 'Main image updated from Mudae', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setMudaeMainBusy(false)
    }
  }

  const runCustomUpload = async (fileList) => {
    const list = dedupeFilesByIdentity(Array.from(fileList)).filter((f) => isImageFileLike(f))
    if (!list.length) {
      addToast('No image files to upload', 'error')
      return
    }
    if (customUploadLockRef.current) {
      addToast('An upload is already in progress', 'info')
      return
    }
    customUploadLockRef.current = true
    const total = list.length
    setCustomUploadProgress({ phase: 'starting', current: 0, total })
    addToast(`Starting upload of ${total} image${total !== 1 ? 's' : ''}…`, 'info')

    const errors = []
    try {
      for (let i = 0; i < list.length; i++) {
        const file = list[i]
        setCustomUploadProgress({ phase: 'uploading', current: i + 1, total, fileName: file.name })
        if (file.size > MAX_CUSTOM_IMAGE_BYTES) {
          const msg = `File too large (max ${MAX_CUSTOM_IMAGE_BYTES / (1024 * 1024)}MB)`
          addToast(`Skipped ${i + 1}/${total} — ${file.name}: ${msg}`, 'error')
          errors.push({ name: file.name, message: msg })
          continue
        }
        try {
          const fd = new FormData()
          fd.append('character_name', name)
          fd.append('files', file)
          const res = await apiClient.addCustomImage(fd)
          if (Array.isArray(res.links) && res.links.length > 0) {
            await appendCustomImageUrls(name, res.links)
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
          'error'
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
        setUploadErrorDialog(detail)
      }
    } catch (err) {
      addToast(`Upload stopped: ${err.message || 'Unknown error'}`, 'error')
    } finally {
      customUploadLockRef.current = false
      setCustomUploadProgress(null)
    }
  }

  const handleAddCustomImage = async (e) => {
    const files = e.target.files
    if (!files?.length) return
    await runCustomUpload(files)
    if (customInputRef.current) customInputRef.current.value = ''
  }

  const runImportFromUrls = async (urls) => {
    const deduped = dedupeImageUrls(urls)
    if (!deduped.length) return
    if (customUploadLockRef.current) {
      addToast('An upload is already in progress', 'info')
      return
    }
    // Web drag often yields duplicate URLs for the same image; max 1 import per web drop only.
    const list = deduped.slice(0, 1)
    customUploadLockRef.current = true
    setCustomUploadProgress({ phase: 'uploading', current: 1, total: 1 })
    addToast(
      deduped.length > 1
        ? 'Importing one image from the web (extra URLs ignored)…'
        : 'Importing image from the web…',
      'info'
    )
    try {
      const res = await apiClient.importCustomImagesFromUrls(name, list)
      if (Array.isArray(res.links) && res.links.length > 0) {
        await appendCustomImageUrls(name, res.links)
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
      customUploadLockRef.current = false
      setCustomUploadProgress(null)
    }
  }

  const handleCustomDrop = async (e) => {
    e.preventDefault()
    e.stopPropagation()
    setCustomDragOver(false)

    const urls = extractImageUrlsFromDataTransfer(e.dataTransfer)
    const raw = e.dataTransfer.files
    const files = Array.from(raw || []).filter((f) => isImageFileLike(f))

    if (reorderMode && reorderDragIndices) {
      if (urls.length === 0 && files.length === 0) return
    }

    if (customUploadLockRef.current) {
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

  /** OS file drags often omit `Files` in types until drop; `dropEffect: none` blocks the drop event — only use move for in-gallery reorder. */
  const handleCustomSectionDragOver = (e) => {
    e.preventDefault()
    const fileDrag = dataTransferIsFileDrag(e.dataTransfer)
    const webDrag = dataTransferHasWebImageDrag(e.dataTransfer)
    const reorderInternal = reorderMode && reorderDragIndices && !fileDrag && !webDrag
    e.dataTransfer.dropEffect = reorderInternal ? 'move' : 'copy'
    setCustomDragOver(true)
  }

  const handleCustomSectionDragLeave = (e) => {
    const next = e.relatedTarget
    if (next && e.currentTarget.contains(next)) return
    setCustomDragOver(false)
  }

  const handleDownloadSelected = async () => {
    if (!selectedUrls.length) {
      addToast('Select at least one image, or tap Select All', 'info')
      return
    }
    try {
      if (typeof window.showDirectoryPicker === 'function') {
        const dirHandle = await window.showDirectoryPicker()
        await writeCustomImagesToDirectory(selectedUrls, dirHandle)
        addToast(`Saved ${selectedUrls.length} image${selectedUrls.length === 1 ? '' : 's'} to the folder you chose`, 'success')
      } else {
        await downloadCustomImagesViaBrowser(selectedUrls)
        addToast(
          'Downloads started. For choosing a folder, use Chrome or Edge. Other browsers save to your default download folder.',
          'info'
        )
      }
      resetModes()
    } catch (e) {
      if (e.name === 'AbortError') return
      addToast(e.message || 'Download failed', 'error')
    }
  }

  const handleDeleteSelected = async () => {
    if (!selectedUrls.length) return
    const orderBeforeDelete = [...customs]
    try {
      await apiClient.deleteCustomImages(name, selectedUrls)
      await loadCustomImagesForCharacter(name)
      const n = selectedUrls.length
      addToast(`${n} custom image${n === 1 ? '' : 's'} removed`, 'success', {
        onUndo: async () => {
          await apiClient.reorderCustomImages(name, orderBeforeDelete)
          await loadCustomImagesForCharacter(name)
          resetModes()
          addToast('Images restored', 'info')
        },
      })
      resetModes()
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const toggleSelect = (url) => {
    if (aiMode || deleteMode || downloadMode || reorderMode) {
      setSelectedUrls((prev) => (prev.includes(url) ? prev.filter((u) => u !== url) : [...prev, url]))
    }
  }

  const selectAllImages = () => {
    setSelectedUrls([...customs])
  }

  const generateAiCommand = () => {
    const urls = selectedUrls.length ? selectedUrls : customs
    const charName = editMode ? editName : char.name
    const cmd = buildAiCommand(charName, urls)
    if (cmd.length < DISCORD_LIMIT_REGULAR) {
      navigator.clipboard
        .writeText(cmd)
        .then(() => {
          addToast('Command copied to clipboard', 'success')
          resetModes()
        })
        .catch(() => addToast('Failed to copy', 'error'))
      return
    }
    const nonNitroParts = splitAiCommandForLimit(charName, urls, DISCORD_LIMIT_REGULAR)
    const nitroParts =
      cmd.length <= DISCORD_LIMIT_NITRO
        ? [cmd]
        : splitAiCommandForLimit(charName, urls, DISCORD_LIMIT_NITRO)
    setAiLimitDialog({
      charCount: cmd.length,
      nonNitroParts,
      nitroParts,
    })
  }

  const closeAiLimitDialog = () => {
    resetModes()
  }

  const onDragStart = (e, index) => {
    if (!reorderMode) return
    beginReorderDrag(index)
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', String(index))
  }

  const clearReorderTouchWindowListeners = () => {
    if (typeof reorderTouchCleanupRef.current === 'function') {
      reorderTouchCleanupRef.current()
      reorderTouchCleanupRef.current = null
    }
  }

  const resolveReorderSlotIndex = (clientX, clientY) => {
    const el = document.elementFromPoint(clientX, clientY)
    const slot = el && el.closest && el.closest('[data-reorder-slot]')
    if (!slot) return null
    const raw = slot.getAttribute('data-reorder-slot')
    const i = raw != null ? Number.parseInt(raw, 10) : NaN
    return Number.isFinite(i) ? i : null
  }

  const onDragOver = (e, index) => {
    const fileDrag = dataTransferIsFileDrag(e.dataTransfer)
    const webDrag = dataTransferHasWebImageDrag(e.dataTransfer)
    const reorderInternal = reorderMode && reorderDragIndices && !fileDrag && !webDrag
    if (reorderInternal) {
      e.preventDefault()
      e.dataTransfer.dropEffect = 'move'
      dragOverRef.current = index
      setReorderDropTargetIndex(index)
      return
    }
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  const onDragEnd = () => {
    const to = dragOverRef.current
    const from = dragItemRef.current
    const indices = dragIndicesRef.current
    dragItemRef.current = null
    dragOverRef.current = null
    dragIndicesRef.current = null
    setReorderDropTargetIndex(null)
    setReorderDragIndices(null)
    if (from == null || to == null || !indices?.length) return
    const next = moveGroupInArray(customs, indices, to)
    if (ordersEqual(next, customs)) return
    applyReorder(next)
  }

  /** Long-press on a tile, then drag with finger (touch — native HTML5 DnD does not work). */
  const onReorderItemTouchStart = (e, index) => {
    if (!reorderMode || e.touches.length !== 1) return
    clearReorderTouchWindowListeners()
    if (typeof reorderTouchCancelPendingRef.current === 'function') {
      reorderTouchCancelPendingRef.current()
      reorderTouchCancelPendingRef.current = null
    }
    const orphan = reorderTouchPendingRef.current
    if (orphan?.timerId) clearTimeout(orphan.timerId)
    reorderTouchPendingRef.current = null
    const t = e.touches[0]
    const startX = t.clientX
    const startY = t.clientY

    const cancelPending = () => {
      reorderTouchCancelPendingRef.current = null
      const pend = reorderTouchPendingRef.current
      if (pend?.timerId) clearTimeout(pend.timerId)
      reorderTouchPendingRef.current = null
      window.removeEventListener('touchmove', onMoveBeforeLongPress)
      window.removeEventListener('touchend', cancelPending)
      window.removeEventListener('touchcancel', cancelPending)
    }
    reorderTouchCancelPendingRef.current = cancelPending

    function onMoveBeforeLongPress(ev) {
      if (ev.touches.length !== 1) {
        cancelPending()
        return
      }
      const tt = ev.touches[0]
      const dx = tt.clientX - startX
      const dy = tt.clientY - startY
      if (dx * dx + dy * dy > REORDER_TOUCH_SLOP_PX * REORDER_TOUCH_SLOP_PX) cancelPending()
    }

    const timerId = setTimeout(() => {
      reorderTouchCancelPendingRef.current = null
      reorderTouchPendingRef.current = null
      window.removeEventListener('touchmove', onMoveBeforeLongPress)
      window.removeEventListener('touchend', cancelPending)
      window.removeEventListener('touchcancel', cancelPending)
      beginReorderDrag(index)
      ignoreNextReorderItemClickRef.current = true
      reorderEdgePointerYRef.current = startY
      dragOverRef.current = index
      setReorderDropTargetIndex(index)

      const onDragTouchMove = (ev) => {
        if (ev.touches.length !== 1) return
        ev.preventDefault()
        const tt = ev.touches[0]
        reorderEdgePointerYRef.current = tt.clientY
        const slotIdx = resolveReorderSlotIndex(tt.clientX, tt.clientY)
        if (slotIdx != null) {
          dragOverRef.current = slotIdx
          setReorderDropTargetIndex(slotIdx)
        }
      }

      const onDragTouchEnd = () => {
        document.body.classList.remove('reorder-touch-dragging')
        window.removeEventListener('touchmove', onDragTouchMove)
        window.removeEventListener('touchend', onDragTouchEnd)
        window.removeEventListener('touchcancel', onDragTouchEnd)
        reorderTouchCleanupRef.current = null
        onDragEnd()
      }

      document.body.classList.add('reorder-touch-dragging')
      window.addEventListener('touchmove', onDragTouchMove, { passive: false })
      window.addEventListener('touchend', onDragTouchEnd)
      window.addEventListener('touchcancel', onDragTouchEnd)
      reorderTouchCleanupRef.current = () => {
        document.body.classList.remove('reorder-touch-dragging')
        window.removeEventListener('touchmove', onDragTouchMove)
        window.removeEventListener('touchend', onDragTouchEnd)
        window.removeEventListener('touchcancel', onDragTouchEnd)
      }
    }, REORDER_LONG_PRESS_MS)

    reorderTouchPendingRef.current = { timerId, index, startX, startY }
    window.addEventListener('touchmove', onMoveBeforeLongPress, { passive: true })
    window.addEventListener('touchend', cancelPending)
    window.addEventListener('touchcancel', cancelPending)
  }

  const onGalleryDragLeave = (e) => {
    if (!reorderMode || !reorderDragIndices) return
    const next = e.relatedTarget
    if (next && e.currentTarget.contains(next)) return
    setReorderDropTargetIndex(null)
    dragOverRef.current = null
  }

  const onGalleryDragOver = (e) => {
    const fileDrag = dataTransferIsFileDrag(e.dataTransfer)
    const webDrag = dataTransferHasWebImageDrag(e.dataTransfer)
    const reorderInternal = reorderMode && reorderDragIndices && !fileDrag && !webDrag
    e.preventDefault()
    e.dataTransfer.dropEffect = reorderInternal ? 'move' : 'copy'
  }

  const openModal = (index) => {
    if (aiMode || deleteMode || downloadMode || reorderMode) return
    setModalIndex(index)
    setModalOpen(true)
  }

  /** Modal viewer: custom images only (main portrait is separate above the gallery) */
  const galleryModalImages = customs.map((u) => getImageUrl(u) || u).filter(Boolean)

  return (
    <div id="selectedCharacter" className="character-page">
      <div className="character-top-section">
      <div id="charInfo" className="char-info-section">
        {!editMode ? (
          <div id="charDisplayMode">
            <h3 id="charNameDisplay" className="display-title">{char.name}</h3>
            <p id="charSeriesDisplay" className="text-body">{char.series || '—'}</p>
            <p id="charRankDisplay" className="text-meta">Rank: {char.rank || '—'}</p>
            <div className="bottom-controls char-page-actions">
              <button type="button" className="action-btn" onClick={() => setEditMode(true)} title="Edit name, series, rank, and main image">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px' }}>
                  <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                  <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                </svg>
                Edit Character
              </button>
              <button type="button" className="action-btn" onClick={() => { resetModes(); setAiMode(true) }}>
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px' }}>
                  <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                  <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                </svg>
                Get $ai Command
              </button>
            </div>
          </div>
        ) : (
          <div id="charEditMode">
            <div className="edit-form-container">
              <div className="edit-group full-width">
                <label htmlFor="editCharName">Name</label>
                <input id="editCharName" type="text" className="modern-input" placeholder="Character Name" value={editName} onChange={(e) => setEditName(e.target.value)} />
              </div>
              <div className="edit-group full-width">
                <label htmlFor="editCharSeries">Series</label>
                <input id="editCharSeries" type="text" className="modern-input" placeholder="Series Name" value={editSeries} onChange={(e) => setEditSeries(e.target.value)} autoComplete="off" />
              </div>
              <div className="edit-group full-width">
                <label htmlFor="editCharRank">Rank</label>
                <input id="editCharRank" type="number" className="modern-input" placeholder="#" value={editRank} onChange={(e) => setEditRank(e.target.value)} />
              </div>
              <div className="edit-actions">
                <button type="button" className="action-btn primary" onClick={handleSaveEdit} disabled={loading}>Save Changes</button>
                <button type="button" className="action-btn secondary" onClick={() => setEditMode(false)}>Cancel</button>
              </div>
            </div>
          </div>
        )}
      </div>
      <div id="charImageContainer" className="char-image-section">
        <div
          className={`image-wrapper ${editMode ? 'edit-mode' : ''} ${dragOver ? 'drag-over-main' : ''}`}
          onClick={() => editMode && mainInputRef.current?.click()}
          onDragOver={(e) => { e.preventDefault(); editMode && setDragOver(true) }}
          onDragLeave={() => setDragOver(false)}
          onDrop={editMode ? handleMainImageDrop : undefined}
          role={editMode ? 'button' : undefined}
          tabIndex={editMode ? 0 : undefined}
          onKeyDown={(e) => editMode && e.key === 'Enter' && mainInputRef.current?.click()}
        >
          <input ref={mainInputRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={handleMainImageChange} />
          {mainImage ? (
            <img id="charImageDisplay" src={getImageUrl(mainImage)} alt={char.name} className="char-main-image-full" />
          ) : (
            <div className="char-main-placeholder">No image</div>
          )}
          {editMode && <div className="image-overlay"><span>Click or Drop to Change</span></div>}
        </div>
        {mudaeConfigured && (
          <div className="mudae-main-actions" style={{ marginTop: '0.65rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="action-btn secondary"
              disabled={mudaeMainBusy || loading}
              onClick={handleMudaeRefreshMain}
              title="Run $im via Mudae and set the card image as main"
            >
              {mudaeMainBusy ? 'Updating from Mudae…' : 'Update main from Mudae'}
            </button>
          </div>
        )}
        <button
          type="button"
          className={`save-button ${isSaved ? 'saved' : ''}`}
          onClick={handleToggleSave}
          title={isSaved ? 'Unsave' : 'Save'}
          aria-label={isSaved ? 'Unsave' : 'Save'}
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
          </svg>
        </button>
      </div>
      </div>

      <div
        id="customImagesSection"
        className={customDragOver ? 'drag-over' : ''}
        onDragOver={handleCustomSectionDragOver}
        onDragLeave={handleCustomSectionDragLeave}
        onDrop={handleCustomDrop}
        style={{ display: 'block' }}
      >
        <div className="custom-images-header-row">
          <h3 className="section-heading custom-images-heading">Custom Images</h3>
          <div className="char-custom-toolbar">
            <div className="char-custom-toolbar-actions" id="char-custom-toolbar-actions">
              {aiMode && (
                <>
                  <button type="button" className="action-btn" onClick={generateAiCommand} style={{ padding: '6px 12px', fontSize: '0.9em', backgroundColor: '#28a745', color: 'white', borderColor: '#28a745' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                    Copy Command ({selectedUrls.length || customs.length})
                  </button>
                  <button type="button" className="action-btn" onClick={selectAllImages} style={{ padding: '6px 12px', fontSize: '0.9em' }}>Select All</button>
                  <button type="button" className="action-btn" onClick={resetModes} style={{ padding: '6px 12px', fontSize: '0.9em' }}>Cancel</button>
                </>
              )}
              {deleteMode && (
                <>
                  <button type="button" className="action-btn" onClick={handleDeleteSelected} style={{ padding: '6px 12px', fontSize: '0.9em', backgroundColor: '#dc3545', color: 'white', borderColor: '#dc3545' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    Delete Selected ({selectedUrls.length})
                  </button>
                  <button type="button" className="action-btn" onClick={resetModes} style={{ padding: '6px 12px', fontSize: '0.9em' }}>Cancel</button>
                </>
              )}
              {downloadMode && (
                <>
                  <button
                    type="button"
                    className="action-btn primary"
                    onClick={handleDownloadSelected}
                    disabled={selectedUrls.length === 0}
                    style={{ padding: '6px 12px', fontSize: '0.9em' }}
                    title={selectedUrls.length === 0 ? 'Select images first' : 'Choose a folder and save files there'}
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Download ({selectedUrls.length})
                  </button>
                  <button type="button" className="action-btn" onClick={selectAllImages} style={{ padding: '6px 12px', fontSize: '0.9em' }}>Select All</button>
                  <button type="button" className="action-btn" onClick={resetModes} style={{ padding: '6px 12px', fontSize: '0.9em' }}>Cancel</button>
                </>
              )}
              {reorderMode && !aiMode && !deleteMode && !downloadMode && (
                <>
                  <button type="button" className="action-btn" onClick={() => setSelectedUrls([])} style={{ padding: '6px 12px', fontSize: '0.9em' }}>
                    Clear selection
                  </button>
                  <button type="button" className="action-btn secondary" onClick={cancelReorder} style={{ padding: '6px 12px', fontSize: '0.9em' }}>
                    Cancel
                  </button>
                  <button type="button" className="action-btn primary" onClick={doneReorder} style={{ padding: '6px 12px', fontSize: '0.9em' }}>
                    Done
                  </button>
                </>
              )}
              {!aiMode && !deleteMode && !downloadMode && !reorderMode && (
                <>
                  <button type="button" className="action-btn" onClick={() => { resetModes(); setDeleteMode(true) }} style={{ padding: '6px 12px', fontSize: '0.9em' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    Delete
                  </button>
                  <button type="button" className="action-btn" onClick={enterDownloadMode} style={{ padding: '6px 12px', fontSize: '0.9em' }} title="Download selected custom images to a folder">
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Download
                  </button>
                  <button type="button" className="action-btn" onClick={enterReorderMode} style={{ padding: '6px 12px', fontSize: '0.9em' }}>
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <polyline points="5 9 2 12 5 15" />
                      <polyline points="9 5 12 2 15 5" />
                      <polyline points="19 9 22 12 19 15" />
                      <polyline points="9 19 12 22 15 19" />
                      <line x1="2" y1="12" x2="22" y2="12" />
                      <line x1="12" y1="2" x2="12" y2="22" />
                    </svg>
                    Reorder
                  </button>
                  <button
                    type="button"
                    className="action-btn"
                    disabled={!!customUploadProgress}
                    onClick={() => customInputRef.current?.click()}
                    style={{ padding: '6px 12px', fontSize: '0.9em', opacity: customUploadProgress ? 0.6 : 1 }}
                    title="Add Custom Image"
                  >
                    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: '5px', verticalAlign: 'text-bottom' }}>
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    Add Image
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
        {reorderMode && (
          <details className="reorder-mode-hint-details">
            <summary className="reorder-mode-hint-summary">How reorder works</summary>
            <div className="reorder-mode-hint-body">
              <p>
                <strong>Desktop:</strong> drag a thumbnail to a new position. The page scrolls when you drag near the top or bottom edge.
              </p>
              <p>
                <strong>Mobile / touch:</strong> <strong>press and hold</strong> a thumbnail until it is picked up, then drag and release where you want it.
              </p>
              <p>
                <strong>Move several at once:</strong> tap images to select them (or Clear selection), then drag any selected image — the whole group moves together.
              </p>
            </div>
          </details>
        )}
        <input ref={customInputRef} type="file" accept="image/*" multiple style={{ display: 'none' }} onChange={handleAddCustomImage} disabled={!!customUploadProgress} />
        <p style={{ textAlign: 'center', color: '#6c757d', margin: '10px 0', fontSize: '0.9em', border: '1px dashed #ccc', padding: '10px', borderRadius: '5px' }}>
          Drag &amp; drop files or images from the web (e.g. Pinterest) here, or click &quot;Add Image&quot;
        </p>
        {customUploadProgress && (
          <div className="custom-upload-progress" role="status" aria-live="polite">
            <span className="custom-upload-progress-spinner" aria-hidden />
            <span className="custom-upload-progress-text">
              {customUploadProgress.phase === 'starting'
                ? `Preparing ${customUploadProgress.total} image${customUploadProgress.total !== 1 ? 's' : ''}…`
                : `Uploading ${customUploadProgress.current}/${customUploadProgress.total}${customUploadProgress.fileName ? ` — ${customUploadProgress.fileName}` : ''}`}
            </span>
          </div>
        )}
        <div
          id="customImagesGallery"
          className={reorderDragIndices ? 'reorder-drag-active' : ''}
          onDragOver={onGalleryDragOver}
          onDragLeave={onGalleryDragLeave}
        >
          {customs.map((url, idx) => {
            const isDropTarget = reorderMode && reorderDropTargetIndex === idx
            const isDragSource = reorderMode && reorderDragIndices?.includes(idx)
            return (
            <div
              key={url}
              data-reorder-slot={idx}
              className={`gallery-item-wrapper ${aiMode ? 'ai-mode' : ''} ${deleteMode ? 'delete-mode' : ''} ${downloadMode ? 'download-mode' : ''} ${reorderMode ? 'reorder-mode' : ''} ${selectedUrls.includes(url) ? 'selected' : ''} ${isDropTarget ? 'reorder-drop-target' : ''} ${isDragSource ? 'reorder-drag-source' : ''}`}
              onClick={() => {
                if (ignoreNextReorderItemClickRef.current) {
                  ignoreNextReorderItemClickRef.current = false
                  return
                }
                if (aiMode || deleteMode || downloadMode || reorderMode) toggleSelect(url)
              }}
              onTouchStart={(e) => reorderMode && onReorderItemTouchStart(e, idx)}
              onDragStart={(e) => onDragStart(e, idx)}
              onDragOver={(e) => onDragOver(e, idx)}
              onDragEnd={onDragEnd}
              draggable={reorderMode}
              role={reorderMode ? 'button' : undefined}
              tabIndex={reorderMode ? 0 : undefined}
            >
              <img
                src={getImageUrl(url)}
                alt=""
                draggable={false}
                className="custom-image-full"
                onClick={() => !aiMode && !deleteMode && !downloadMode && !reorderMode && openModal(idx)}
              />
              {isDropTarget && (
                <span className="reorder-drop-label" aria-hidden>
                  Drop here
                </span>
              )}
            </div>
            )
          })}
        </div>
      </div>

      {modalOpen && (
        <ImageModal
          images={galleryModalImages}
          currentIndex={modalIndex}
          onClose={() => setModalOpen(false)}
          onPrev={() => setModalIndex((i) => Math.max(0, i - 1))}
          onNext={() => setModalIndex((i) => Math.min(galleryModalImages.length - 1, i + 1))}
        />
      )}
      {uploadErrorDialog && (
        <UploadErrorDialog
          title="Upload issue"
          body={uploadErrorDialog}
          onClose={() => setUploadErrorDialog(null)}
        />
      )}
      {aiLimitDialog && (
        <AiCommandLimitDialog
          charCount={aiLimitDialog.charCount}
          nonNitroParts={aiLimitDialog.nonNitroParts}
          nitroParts={aiLimitDialog.nitroParts}
          onClose={closeAiLimitDialog}
        />
      )}
    </div>
  )
}

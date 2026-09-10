import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import AiCommandLimitDialog from '../components/AiCommandLimitDialog'
import ImageModal from '../components/ImageModal'
import RemovedDrawer from '../components/RemovedDrawer'
import ReportDialog from '../components/ReportDialog'
import UploadErrorDialog from '../components/UploadErrorDialog'
import { Button, Card, ConfirmDialog, IconButton } from '../components/ui'
import { apiUrl } from '../config'
import { useGalleryReorder } from '../hooks/useGalleryReorder'
import { useStore } from '../store/useStore'
import {
  buildAiCommand,
  DISCORD_LIMIT_NITRO,
  DISCORD_LIMIT_REGULAR,
  splitAiCommandForLimit,
} from '../utils/aiCommandDiscord'
import {
  downloadCustomImagesViaBrowser,
  writeCustomImagesToDirectory,
} from '../utils/downloadCustomImages'
import {
  dataTransferHasWebImageDrag,
  dedupeImageUrls,
  extractImageUrlsFromDataTransfer,
} from '../utils/dragImageUrls'
import { FILLERS, ratioFor, ratioOf } from '../utils/galleryRatios'
import {
  dataTransferIsFileDrag,
  dedupeFilesByIdentity,
  isImageFileLike,
  MAX_CUSTOM_IMAGE_BYTES,
} from '../utils/imageFiles'

export default function CharacterPage() {
  const { name } = useParams()
  const navigate = useNavigate()
  const characters = useStore((s) => s.characters)
  const savedCharacters = useStore((s) => s.savedCharacters)
  const characterImages = useStore((s) => s.characterImages)
  const loadCustomImagesForCharacter = useStore((s) => s.loadCustomImagesForCharacter)
  const appendCustomImageUrls = useStore((s) => s.appendCustomImageUrls)
  const loadCharacters = useStore((s) => s.loadCharacters)
  const loadSaved = useStore((s) => s.loadSaved)
  const renameCustomCharacterData = useStore((s) => s.renameCustomCharacterData)
  const saveCharacter = useStore((s) => s.saveCharacter)
  const removeSaved = useStore((s) => s.removeSaved)
  const addToast = useStore((s) => s.addToast)

  const char =
    characters.find((c) => c.name === name) || savedCharacters.find((c) => c.name === name)
  const isSaved = savedCharacters.some((s) => s.name === name)

  const [showHidden, setShowHidden] = useState(false)
  const allRows = characterImages[name] || []
  const hiddenCount = allRows.filter((row) => row.hidden).length
  // Hidden images drop out of the gallery entirely unless you ask for them.
  // That is the whole value of hide-for-me: it has to actually get them out of
  // the way, or people go back to deleting other people's images.
  const rows = showHidden ? allRows : allRows.filter((row) => !row.hidden)
  const customs = rows.map((row) => row.url)
  const rowByUrl = new Map(allRows.map((row) => [row.url, row]))

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
  const [confirmRemove, setConfirmRemove] = useState(null)
  const [reportTarget, setReportTarget] = useState(null)
  const [removedDrawer, setRemovedDrawer] = useState(null)
  // Measured as images load; see utils/galleryRatios.js for why the server
  // cannot supply these.
  const [ratios, setRatios] = useState({})
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
  /** Snapshot of the order when reorder mode opened, so Cancel can restore it. */
  const reorderSessionBaselineRef = useRef(null)

  useEffect(() => {
    if (char) {
      setEditName(char.name)
      setEditSeries(char.series || '')
      setEditRank(char.rank || '')
      setMainImage(char.image || '')
    }
  }, [char])

  useEffect(() => {
    apiClient
      .mudaeStatus()
      .then((r) => setMudaeConfigured(!!r.configured))
      .catch(() => setMudaeConfigured(false))
  }, [])

  useEffect(() => {
    loadCustomImagesForCharacter(name)
  }, [name, loadCustomImagesForCharacter])

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
      addToast('Order reverted to before you started reordering.', 'info')
    } catch (e) {
      addToast(e.message || 'Could not revert order', 'error')
    }
  }, [name, loadCustomImagesForCharacter, addToast])

  const doneReorder = useCallback(() => {
    reorderSessionBaselineRef.current = null
    setReorderMode(false)
    setSelectedUrls([])
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
    [customs, selectedUrls],
  )

  const reorder = useGalleryReorder({
    items: customs,
    enabled: reorderMode,
    indicesFor: getIndicesToMove,
    onReorder: (next) => applyReorder(next),
  })

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
    [name, loadCustomImagesForCharacter, addToast],
  )

  if (!char) return <div className="loading">Character not found</div>

  const handleSaveEdit = async () => {
    setLoading(true)
    try {
      await apiClient.editCharacter({
        original_name: name,
        new_name: editName,
        series: editSeries,
        rank: editRank,
      })
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
    apiClient
      .setMainImage(fd)
      .then((res) => {
        setMainImage(res.image_url)
        addToast('Main image updated', 'success')
      })
      .catch((err) => addToast(err.message, 'error'))
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
      'info',
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

  const recordTakes = (urls, kind) => {
    const ids = urls.map((url) => rowByUrl.get(url)?.id).filter((id) => id != null)
    if (ids.length) apiClient.recordTakes(ids, kind)
  }

  const handleDownloadSelected = async () => {
    if (!selectedUrls.length) {
      addToast('Select at least one image, or tap Select All', 'info')
      return
    }
    recordTakes(selectedUrls, 'download')
    try {
      if (typeof window.showDirectoryPicker === 'function') {
        const dirHandle = await window.showDirectoryPicker()
        await writeCustomImagesToDirectory(selectedUrls, dirHandle)
        addToast(
          `Saved ${selectedUrls.length} image${selectedUrls.length === 1 ? '' : 's'} to the folder you chose`,
          'success',
        )
      } else {
        await downloadCustomImagesViaBrowser(selectedUrls)
        addToast(
          'Downloads started. For choosing a folder, use Chrome or Edge. Other browsers save to your default download folder.',
          'info',
        )
      }
      resetModes()
    } catch (e) {
      if (e.name === 'AbortError') return
      addToast(e.message || 'Download failed', 'error')
    }
  }

  // You can only remove what you added, so a selection splits in two and the
  // toolbar has to offer both actions. DECISIONS.md section 1.
  const selectedRows = selectedUrls.map((url) => rowByUrl.get(url)).filter(Boolean)
  const mineSelected = selectedRows.filter((row) => row.is_mine)
  const othersSelected = selectedRows.filter((row) => !row.is_mine)

  const removeOwnImages = async () => {
    setConfirmRemove(null)
    const urls = mineSelected.map((row) => row.url)
    if (!urls.length) return
    try {
      const result = await apiClient.deleteCustomImages(name, urls)
      await loadCustomImagesForCharacter(name)
      const removed = result?.removed?.length ?? urls.length
      addToast(`${removed} image${removed === 1 ? '' : 's'} removed`, 'success', {
        onUndo: async () => {
          // Restore, not reorder. The old undo wrote a stale array back through
          // reorderCustomImages, which clobbered anyone else's concurrent edits
          // and could not bring a removed image back at all.
          await apiClient.restoreImages(name, urls)
          await loadCustomImagesForCharacter(name)
          addToast('Images restored', 'info')
        },
      })
      resetModes()
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleRemoveSelected = () => {
    if (!mineSelected.length) return
    setConfirmRemove(mineSelected.length)
  }

  const handleHideSelected = async () => {
    const ids = othersSelected.map((row) => row.id)
    if (!ids.length) return
    try {
      await apiClient.hideImages(ids)
      await loadCustomImagesForCharacter(name)
      addToast(`${ids.length} image${ids.length === 1 ? '' : 's'} hidden for you`, 'success', {
        onUndo: async () => {
          await apiClient.unhideImages(ids)
          await loadCustomImagesForCharacter(name)
          addToast('Images shown again', 'info')
        },
      })
      resetModes()
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const handleUnhideAll = async () => {
    const ids = allRows.filter((row) => row.hidden).map((row) => row.id)
    if (!ids.length) return
    try {
      await apiClient.unhideImages(ids)
      await loadCustomImagesForCharacter(name)
      addToast('Hidden images restored to your view', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const openRemovedDrawer = async () => {
    try {
      setRemovedDrawer(await apiClient.getRemovedImages(name))
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const noteRatio = (imageId, element) => {
    const ratio = ratioOf(element)
    if (ratio === null) return
    setRatios((prev) => (prev[imageId] === ratio ? prev : { ...prev, [imageId]: ratio }))
  }

  const handleReport = async (imageId, reason) => {
    setReportTarget(null)
    try {
      const result = await apiClient.reportImage(imageId, reason)
      await loadCustomImagesForCharacter(name)
      if (result.removed) {
        addToast('Reported. That was the second report, so the image was removed.', 'success')
      } else if (result.already_reported) {
        addToast('You have already reported this image', 'info')
      } else {
        addToast('Reported. One more report from someone else will remove it.', 'success')
      }
    } catch (err) {
      addToast(err.message, 'error')
    }
  }

  const toggleSelect = (url) => {
    if (aiMode || deleteMode || downloadMode || reorderMode) {
      setSelectedUrls((prev) =>
        prev.includes(url) ? prev.filter((u) => u !== url) : [...prev, url],
      )
    }
  }

  const selectAllImages = () => {
    setSelectedUrls([...customs])
  }

  const generateAiCommand = () => {
    const urls = selectedUrls.length ? selectedUrls : customs
    const charName = editMode ? editName : char.name
    recordTakes(urls, 'copy_command')
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

  /**
   * Reordering no longer travels over HTML5 drag-and-drop, so a drag reaching
   * the gallery can only have come from outside — a file, or an image dragged
   * in from a web page. No inspection of dataTransfer is needed to tell them
   * apart any more.
   */
  const onGalleryDragOver = (e) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'copy'
  }

  const openModal = (index) => {
    if (aiMode || deleteMode || downloadMode || reorderMode) return
    setModalIndex(index)
    setModalOpen(true)
  }

  /** Modal viewer: custom images only (main portrait is separate above the gallery) */
  const galleryModalImages = customs.map((u) => getImageUrl(u) || u).filter(Boolean)

  return (
    <Card as="article" padding="lg" className="character-page">
      <div className="character-top-section">
        <div className="char-info-section">
          {!editMode ? (
            <div id="charDisplayMode">
              <h3 id="charNameDisplay" className="display-title">
                {char.name}
              </h3>
              <p id="charSeriesDisplay" className="text-body">
                {char.series || '—'}
              </p>
              <p id="charRankDisplay" className="text-meta">
                Rank: {char.rank || '—'}
              </p>
              <div className="char-page-actions">
                <Button
                  variant="secondary"
                  onClick={() => setEditMode(true)}
                  title="Edit name, series, rank, and main image"
                >
                  <svg
                    aria-hidden="true"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
                  </svg>
                  Edit Character
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    resetModes()
                    setAiMode(true)
                  }}
                >
                  <svg
                    aria-hidden="true"
                    width="16"
                    height="16"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                  </svg>
                  Get $ai Command
                </Button>
              </div>
            </div>
          ) : (
            <div id="charEditMode">
              <div className="edit-form-container">
                <div className="edit-group full-width">
                  <label htmlFor="editCharName">Name</label>
                  <input
                    id="editCharName"
                    type="text"
                    className="modern-input"
                    placeholder="Character Name"
                    value={editName}
                    onChange={(e) => setEditName(e.target.value)}
                  />
                </div>
                <div className="edit-group full-width">
                  <label htmlFor="editCharSeries">Series</label>
                  <input
                    id="editCharSeries"
                    type="text"
                    className="modern-input"
                    placeholder="Series Name"
                    value={editSeries}
                    onChange={(e) => setEditSeries(e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="edit-group full-width">
                  <label htmlFor="editCharRank">Rank</label>
                  <input
                    id="editCharRank"
                    type="number"
                    className="modern-input"
                    placeholder="#"
                    value={editRank}
                    onChange={(e) => setEditRank(e.target.value)}
                  />
                </div>
                <div className="edit-actions">
                  <Button variant="primary" onClick={handleSaveEdit} disabled={loading}>
                    Save Changes
                  </Button>
                  <Button variant="secondary" onClick={() => setEditMode(false)}>
                    Cancel
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
        <div className="char-image-section">
          <div
            className={`image-wrapper ${editMode ? 'edit-mode' : ''} ${dragOver ? 'drag-over-main' : ''}`}
            onClick={() => editMode && mainInputRef.current?.click()}
            onDragOver={(e) => {
              e.preventDefault()
              editMode && setDragOver(true)
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={editMode ? handleMainImageDrop : undefined}
            role={editMode ? 'button' : undefined}
            tabIndex={editMode ? 0 : undefined}
            onKeyDown={(e) => editMode && e.key === 'Enter' && mainInputRef.current?.click()}
          >
            <input
              ref={mainInputRef}
              type="file"
              accept="image/*"
              style={{ display: 'none' }}
              onChange={handleMainImageChange}
            />
            {mainImage ? (
              <img
                id="charImageDisplay"
                src={getImageUrl(mainImage)}
                alt={char.name}
                className="char-main-image-full"
              />
            ) : (
              <div className="char-main-placeholder">No image</div>
            )}
            {editMode && (
              <div className="image-overlay">
                <span>Click or Drop to Change</span>
              </div>
            )}
          </div>
          {mudaeConfigured && (
            <div className="char-mudae-actions">
              <Button
                variant="secondary"
                disabled={mudaeMainBusy || loading}
                onClick={handleMudaeRefreshMain}
                title="Run $im via Mudae and set the card image as main"
              >
                {mudaeMainBusy ? 'Updating from Mudae…' : 'Update main from Mudae'}
              </Button>
            </div>
          )}
          <IconButton
            className={`save-button ${isSaved ? 'saved' : ''}`}
            onClick={handleToggleSave}
            label={isSaved ? 'Remove from saved' : 'Save this character'}
            aria-pressed={isSaved}
          >
            <svg
              aria-hidden="true"
              width="18"
              height="18"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
          </IconButton>
        </div>
      </div>

      <div
        className={`custom-images-section ${customDragOver ? 'drag-over' : ''}`}
        onDragOver={handleCustomSectionDragOver}
        onDragLeave={handleCustomSectionDragLeave}
        onDrop={handleCustomDrop}
      >
        <div className="custom-images-header-row">
          <h3 className="section-heading custom-images-heading">Custom Images</h3>
          <div className="char-custom-toolbar">
            <div className="char-custom-toolbar-actions" id="char-custom-toolbar-actions">
              {aiMode && (
                <>
                  <Button variant="success" size="sm" onClick={generateAiCommand}>
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
                      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
                    </svg>
                    Copy Command ({selectedUrls.length || customs.length})
                  </Button>
                  <Button variant="secondary" size="sm" onClick={selectAllImages}>
                    Select All
                  </Button>
                  <Button variant="secondary" size="sm" onClick={resetModes}>
                    Cancel
                  </Button>
                </>
              )}
              {deleteMode && (
                <>
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={handleRemoveSelected}
                    disabled={mineSelected.length === 0}
                    title={
                      mineSelected.length === 0
                        ? 'You can only remove images you added'
                        : 'Remove your own images'
                    }
                  >
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    Remove mine ({mineSelected.length})
                  </Button>
                  <Button
                    size="sm"
                    onClick={handleHideSelected}
                    disabled={othersSelected.length === 0}
                    title={
                      othersSelected.length === 0
                        ? "Select someone else's image to hide it"
                        : 'Hide these for you only. Nobody else is affected.'
                    }
                  >
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
                      <line x1="1" y1="1" x2="23" y2="23" />
                    </svg>
                    Hide theirs ({othersSelected.length})
                  </Button>
                  <Button variant="secondary" size="sm" onClick={resetModes}>
                    Cancel
                  </Button>
                </>
              )}
              {downloadMode && (
                <>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleDownloadSelected}
                    disabled={selectedUrls.length === 0}
                    title={
                      selectedUrls.length === 0
                        ? 'Select images first'
                        : 'Choose a folder and save files there'
                    }
                  >
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Download ({selectedUrls.length})
                  </Button>
                  <Button variant="secondary" size="sm" onClick={selectAllImages}>
                    Select All
                  </Button>
                  <Button variant="secondary" size="sm" onClick={resetModes}>
                    Cancel
                  </Button>
                </>
              )}
              {reorderMode && !aiMode && !deleteMode && !downloadMode && (
                <>
                  <Button variant="secondary" size="sm" onClick={() => setSelectedUrls([])}>
                    Clear selection
                  </Button>
                  <Button variant="secondary" size="sm" onClick={cancelReorder}>
                    Cancel
                  </Button>
                  <Button variant="primary" size="sm" onClick={doneReorder}>
                    Done
                  </Button>
                </>
              )}
              {!aiMode && !deleteMode && !downloadMode && !reorderMode && hiddenCount > 0 && (
                <Button
                  size="sm"
                  onClick={() => setShowHidden((v) => !v)}
                  title="Images you have hidden are only hidden for you"
                >
                  {showHidden ? 'Hide them again' : `Show ${hiddenCount} hidden`}
                </Button>
              )}
              {!aiMode && !deleteMode && !downloadMode && !reorderMode && showHidden && (
                <Button size="sm" onClick={handleUnhideAll}>
                  Unhide all ({hiddenCount})
                </Button>
              )}
              {!aiMode && !deleteMode && !downloadMode && !reorderMode && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={openRemovedDrawer}
                  title="Nothing is deleted permanently — see what was removed and put it back"
                >
                  Removed
                </Button>
              )}
              {!aiMode && !deleteMode && !downloadMode && !reorderMode && (
                <>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      resetModes()
                      setDeleteMode(true)
                    }}
                  >
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <polyline points="3 6 5 6 21 6" />
                      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                    </svg>
                    Remove or hide
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={enterDownloadMode}
                    title="Download selected custom images to a folder"
                  >
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                      <polyline points="7 10 12 15 17 10" />
                      <line x1="12" y1="15" x2="12" y2="3" />
                    </svg>
                    Download
                  </Button>
                  <Button variant="secondary" size="sm" onClick={enterReorderMode}>
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <polyline points="5 9 2 12 5 15" />
                      <polyline points="9 5 12 2 15 5" />
                      <polyline points="19 9 22 12 19 15" />
                      <polyline points="9 19 12 22 15 19" />
                      <line x1="2" y1="12" x2="22" y2="12" />
                      <line x1="12" y1="2" x2="12" y2="22" />
                    </svg>
                    Reorder
                  </Button>
                  <Button
                    variant="secondary"
                    size="sm"
                    disabled={!!customUploadProgress}
                    onClick={() => customInputRef.current?.click()}
                    title="Add Custom Image"
                  >
                    <svg
                      aria-hidden="true"
                      width="16"
                      height="16"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                    >
                      <line x1="12" y1="5" x2="12" y2="19" />
                      <line x1="5" y1="12" x2="19" y2="12" />
                    </svg>
                    Add Image
                  </Button>
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
                <strong>Desktop:</strong> drag a thumbnail to a new position. The page scrolls when
                you drag near the top or bottom edge.
              </p>
              <p>
                <strong>Mobile / touch:</strong> <strong>press and hold</strong> a thumbnail until
                it is picked up, then drag and release where you want it.
              </p>
              <p>
                <strong>Move several at once:</strong> tap images to select them (or Clear
                selection), then drag any selected image — the whole group moves together.
              </p>
            </div>
          </details>
        )}
        <input
          ref={customInputRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: 'none' }}
          onChange={handleAddCustomImage}
          disabled={!!customUploadProgress}
        />
        <p className="gallery-drop-hint">
          Drag &amp; drop files or images from the web (e.g. Pinterest) here, or click &quot;Add
          Image&quot;
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
          className={`custom-images-gallery ${reorder.isDragging ? 'reorder-drag-active' : ''}`}
          onDragOver={onGalleryDragOver}
        >
          {rows.map((row, idx) => {
            const url = row.url
            const isDropTarget = reorderMode && reorder.dropTargetIndex === idx
            const isDragSource = reorderMode && reorder.dragIndices?.includes(idx)
            const attribution = row.is_mine
              ? 'Added by you'
              : row.owner
                ? `Added by ${row.owner}`
                : 'Added before ownership was tracked'
            return (
              <div
                key={url}
                data-reorder-slot={idx}
                // The measured shape drives the row maths, so it has to reach
                // CSS somehow; a custom property keeps the rules themselves in
                // the stylesheet.
                style={{ '--ratio': ratioFor(row, ratios[row.id]) }}
                className={`gallery-item-wrapper ${aiMode ? 'ai-mode' : ''} ${deleteMode ? 'delete-mode' : ''} ${downloadMode ? 'download-mode' : ''} ${reorderMode ? 'reorder-mode' : ''} ${selectedUrls.includes(url) ? 'selected' : ''} ${isDropTarget ? 'reorder-drop-target' : ''} ${isDragSource ? 'reorder-drag-source' : ''} ${row.is_mine ? 'is-mine' : ''} ${row.hidden ? 'is-hidden' : ''}`}
                title={attribution}
                onClick={() => {
                  // A drag ends with a synthetic click on whatever the pointer
                  // was over; that must not toggle a selection.
                  if (reorder.consumeClickAfterDrag()) return
                  if (aiMode || deleteMode || downloadMode || reorderMode) toggleSelect(url)
                }}
                {...reorder.itemProps(idx)}
                role={reorderMode ? 'button' : undefined}
                tabIndex={reorderMode ? 0 : undefined}
              >
                <img
                  /*
                    The grid renders a small WebP; `url` stays the canonical
                    ImgChest PNG and is what the lightbox, the download and every
                    $ai command use, because Mudae accepts nothing else. Falls
                    back to the original for GIFs, which are not thumbnailed.
                  */
                  src={row.thumb ? apiUrl(row.thumb) : getImageUrl(url)}
                  alt=""
                  draggable={false}
                  className="custom-image-full"
                  /* A character can hold hundreds of images at ~1.9 MB each, so
                     fetching them all on load is untenable on a slow connection.
                     The row is already the right shape from the stored
                     dimensions, so nothing moves when one arrives. */
                  loading="lazy"
                  decoding="async"
                  width={row.width || undefined}
                  height={row.height || undefined}
                  onLoad={(e) => noteRatio(row.id, e.currentTarget)}
                  onClick={() =>
                    !aiMode && !deleteMode && !downloadMode && !reorderMode && openModal(idx)
                  }
                />
                {deleteMode && (
                  <span className={`gallery-owner-tag ${row.is_mine ? 'is-mine' : ''}`}>
                    {row.is_mine ? 'Yours' : row.owner || 'No owner'}
                  </span>
                )}
                {row.hidden && <span className="gallery-owner-tag is-hidden">Hidden</span>}
                {isDropTarget && (
                  <span className="reorder-drop-label" aria-hidden>
                    Drop here
                  </span>
                )}
              </div>
            )
          })}
          {/*
            Absorb the leftover space on the last row. Without these, flex-grow
            stretches a single trailing image across the full width, which reads
            as a bug rather than a layout. Zero height and no reorder slot, so
            they are inert to both layout and hit-testing.
          */}
          {rows.length > 0 &&
            FILLERS.map((id) => (
              <span key={`filler-${id}`} className="gallery-filler" aria-hidden="true" />
            ))}
        </div>
      </div>

      {modalOpen && (
        <ImageModal
          images={galleryModalImages}
          currentIndex={modalIndex}
          onClose={() => setModalOpen(false)}
          onPrev={() => setModalIndex((i) => Math.max(0, i - 1))}
          onNext={() => setModalIndex((i) => Math.min(galleryModalImages.length - 1, i + 1))}
          onReport={rows[modalIndex] ? () => setReportTarget(rows[modalIndex]) : undefined}
        />
      )}
      {confirmRemove !== null && (
        <ConfirmDialog
          title={`Remove ${confirmRemove} image${confirmRemove === 1 ? '' : 's'}?`}
          body={
            <>
              These are yours to remove. They move to the Removed list rather than being deleted, so
              you or anyone else can restore them later.
            </>
          }
          confirmLabel="Remove"
          variant="danger"
          onConfirm={removeOwnImages}
          onCancel={() => setConfirmRemove(null)}
        />
      )}
      {reportTarget && (
        <ReportDialog
          onSubmit={(reason) => handleReport(reportTarget.id, reason)}
          onCancel={() => setReportTarget(null)}
        />
      )}
      {removedDrawer && (
        <RemovedDrawer
          characterName={name}
          items={removedDrawer}
          onRestore={async (url) => {
            await apiClient.restoreImages(name, [url])
            await loadCustomImagesForCharacter(name)
            addToast('Image restored', 'success')
          }}
          onClose={() => setRemovedDrawer(null)}
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
    </Card>
  )
}

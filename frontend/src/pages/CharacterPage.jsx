import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import AiCommandLimitDialog from '../components/AiCommandLimitDialog'
import { CharacterHeader } from '../components/CharacterHeader'
import CharacterLoadingState from '../components/CharacterLoadingState'
import CustomImageGallery from '../components/CustomImageGallery'
import DuplicateDialog from '../components/DuplicateDialog'
import { GallerySelectionBar } from '../components/GallerySelectionBar'
import { GalleryToolbar } from '../components/GalleryToolbar'
import ImageModal from '../components/ImageModal'
import RemovedDrawer from '../components/RemovedDrawer'
import ReportDialog from '../components/ReportDialog'
import SignInPrompt from '../components/SignInPrompt'
import UploadErrorDialog from '../components/UploadErrorDialog'
import { Button, Card, ConfirmDialog, EmptyState } from '../components/ui'
import { useAccentOverride } from '../hooks/useAccentOverride'
import { useApplyCharacterTheme } from '../hooks/useApplyCharacterTheme'
import { useCharacterEdit } from '../hooks/useCharacterEdit'
import { useCharacterTheme } from '../hooks/useCharacterTheme'
import { useCustomImageUpload } from '../hooks/useCustomImageUpload'
import { useGalleryReorder } from '../hooks/useGalleryReorder'
import { useGallerySelection } from '../hooks/useGallerySelection'
import { useLightbox } from '../hooks/useLightbox'
import { useMainImage } from '../hooks/useMainImage'
import { useMediaQuery } from '../hooks/useMediaQuery'
import {
  applyOrderToCache,
  characterImagesKey,
  useCharacterImages,
} from '../queries/characterImages'
import { useMe } from '../queries/me'
import { savedKey, useRemoveSaved, useSaveCharacter, useSavedCharacters } from '../queries/saved'
import { useStore } from '../store/useStore'
import {
  buildAiCommand,
  capAiImages,
  DISCORD_LIMIT_NITRO,
  DISCORD_LIMIT_REGULAR,
  splitAiCommandForLimit,
} from '../utils/aiCommandDiscord'
import { keysToTraits } from '../utils/characterTraits'
import {
  downloadCustomImagesViaBrowser,
  writeCustomImagesToDirectory,
} from '../utils/downloadCustomImages'

/** What the heading says while a mode is active. Browse gets nothing. */
const MODE_LABELS = {
  select: 'selecting images',
  reorder: 'reordering',
}

/** The phone boundary, shared with the gallery's own column layout. */
const NARROW = '(max-width: 768px)'

export default function CharacterPage() {
  const { name } = useParams()
  const navigate = useNavigate()
  const isNarrow = useMediaQuery(NARROW)
  const { data: savedCharacters = [] } = useSavedCharacters()
  const saveCharacter = useSaveCharacter()
  const removeSaved = useRemoveSaved()
  const { data: me } = useMe()
  const addToast = useStore((s) => s.addToast)
  // Adding an image needs a linked Discord account; everything else does not.
  const canAddImages = Boolean(me?.signed_in)
  const queryClient = useQueryClient()
  // The gallery is server state, cached and invalidated by key rather than kept
  // in the store and refetched by hand after every mutation. The first fetch is
  // still settling only while the query is pending with no data; a cached slice
  // is served immediately, empty or not.
  const { data: imagesData, isPending: imagesPending } = useCharacterImages(name)
  const allRows = imagesData?.rows ?? []
  const galleryLoading = Boolean(name) && imagesPending
  const refreshImages = useCallback(
    () => queryClient.invalidateQueries({ queryKey: characterImagesKey(name) }),
    [queryClient, name],
  )

  // The roster is no longer downloaded, so the page fetches the one character
  // it is showing. A catalog-only name (never added) is treated as not found;
  // search sends those to the Add form instead.
  const [char, setChar] = useState(null)
  const [charLoading, setCharLoading] = useState(true)
  const [charVersion, setCharVersion] = useState(0)
  const reloadChar = () => setCharVersion((v) => v + 1)
  const isSaved = savedCharacters.some((s) => s.name === name)

  const [showHidden, setShowHidden] = useState(false)
  /**
   * Which copy history the "already used" helpers select from: `ever` (every
   * image copied here) or `last` (only the most recent copy). Declared up here
   * with the other page state, not beside the values it feeds, because the page
   * returns early while loading and a hook below that return would change hook
   * order between renders.
   */
  const [copiedScope, setCopiedScope] = useState('ever')
  const hiddenCount = allRows.filter((row) => row.hidden).length
  // Hidden images drop out of the gallery entirely unless you ask for them.
  // That is the whole value of hide-for-me: it has to actually get them out of
  // the way, or people go back to deleting other people's images.
  const rows = showHidden ? allRows : allRows.filter((row) => !row.hidden)
  const customs = rows.map((row) => row.url)
  const rowByUrl = new Map(allRows.map((row) => [row.url, row]))

  // The editor's own state (fields, mode, seeding) lives in the hook; the page
  // keeps only what it does with them.
  const {
    editMode,
    setEditMode,
    editName,
    setEditName,
    editSeries,
    setEditSeries,
    editRank,
    setEditRank,
    editTraits,
    toggleEditTrait,
  } = useCharacterEdit(char)
  const [mainImage, setMainImage] = useState('')
  // The catalog's mirrored portrait applies only while the main image is still
  // the catalog's own; an upload or an edit replaces it and has no mirror.
  const mainThumb = char && mainImage === char.image ? char.image_thumb : ''
  // Above the early returns: hooks must run in the same order every render.
  // The seed is the server-measured accent (see useCharacterTheme); the
  // character list carries it, and the gallery response refreshes it after
  // any change to the images it was measured from. Turning character accents
  // off in settings discards it here as well as on the server, so a row that
  // already carries a seed is never applied against the viewer's choice.
  const characterAccents = me?.settings?.character_accents !== false
  // The gallery response is freshest: the server re-measures the seed from the
  // images that response carried. The saved row's seed covers the moment before
  // the gallery has arrived.
  const savedSeed = savedCharacters.find((s) => s.name === name)?.accent_seed
  const seededAccent = imagesData?.accentSeed ?? savedSeed ?? char?.accent_seed ?? null
  const theme = useCharacterTheme(name, characterAccents ? seededAccent : null)
  useApplyCharacterTheme(theme)
  // Above the early returns, like every hook. Refreshes the gallery and saved
  // rows so the new colour is measured again.
  const accent = useAccentOverride({
    name,
    addToast,
    onChanged: async () => {
      await queryClient.invalidateQueries({ queryKey: characterImagesKey(name) })
      await queryClient.invalidateQueries({ queryKey: savedKey })
      reloadChar()
    },
  })
  const [loading, setLoading] = useState(false)
  const [mudaeConfigured, setMudaeConfigured] = useState(false)
  /**
   * The gallery is in exactly one mode at a time, and its selection and discard
   * confirmation belong to that machine rather than to separate flags. See
   * useGallerySelection.
   */
  const {
    mode,
    selectMode,
    reorderMode,
    selectedUrls,
    confirmDiscardOrder,
    reset: resetSelection,
    enterSelect,
    enterReorder,
    toggleUrl,
    setSelection,
    askDiscard,
    cancelDiscard,
  } = useGallerySelection()
  const [aiLimitDialog, setAiLimitDialog] = useState(null)
  const [confirmRemove, setConfirmRemove] = useState(null)
  const [reportTarget, setReportTarget] = useState(null)
  const [removedDrawer, setRemovedDrawer] = useState(null)

  /** Full multi-line upload error for dismissible dialog (replaces window.alert). */

  const mainInputRef = useRef(null)
  const customInputRef = useRef(null)
  /**
   * Everything one reorder session needs in order to finish or undo itself:
   * `baseline` is the order it opened on, `dirty` whether anything moved,
   * `failed` whether a save came back an error, and `save` the chain those
   * saves run on.
   *
   * Chained rather than parallel: each drop POSTs the whole order, and two of
   * those in flight at once can arrive in either order, which would leave the
   * server holding an order the person did not finish with — and the gallery,
   * which now updates locally, would disagree with it silently until the next
   * reload. Null whenever reorder mode is closed.
   */
  const reorderSessionRef = useRef(null)

  // The full-screen viewer, and the ratios the gallery is laid out from. Opens
  // only from browse; in any other mode a click is a selection.
  const {
    open: modalOpen,
    index: modalIndex,
    ratios,
    noteRatio,
    openAt: openModal,
    close: closeModal,
    prev: prevImage,
    next: nextImage,
  } = useLightbox({ imageCount: customs.length, canOpen: mode === 'browse' })

  useEffect(() => {
    if (char) setMainImage(char.image || '')
  }, [char])

  // charVersion is a re-run trigger, not a value the effect reads.
  // biome-ignore lint/correctness/useExhaustiveDependencies: trigger, not an input
  useEffect(() => {
    let cancelled = false
    setCharLoading(true)
    apiClient
      .findCatalogCharacter(name)
      .then((res) => {
        if (!cancelled) setChar(res?.found && res.character?.in_library ? res.character : null)
      })
      .catch(() => {
        if (!cancelled) setChar(null)
      })
      .finally(() => {
        if (!cancelled) setCharLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [name, charVersion])

  useEffect(() => {
    apiClient
      .mudaeStatus()
      .then((r) => setMudaeConfigured(!!r.configured))
      .catch(() => setMudaeConfigured(false))
  }, [])

  // Counted at most once per person per character per hour on the server, so
  // this firing again on a remount costs nothing.
  useEffect(() => {
    apiClient.recordView(name)
  }, [name])

  const resetModes = useCallback(() => {
    resetSelection()
    setAiLimitDialog(null)
    reorderSessionRef.current = null
  }, [resetSelection])

  /**
   * One selection mode, entered before any verb is chosen.
   *
   * There were four of these — one per verb — and choosing between them meant
   * deciding what you were going to do before you had picked anything to do it
   * to. Now the images come first and the bar offers whatever fits them.
   *
   * `preselect` is what the $ai door hands over. A button that copies a command
   * for every image the moment it is clicked gives you no way to mean "all but
   * those three", and a command is exactly the thing people want to trim. So it
   * opens the selection with everything already chosen: copying all of them is
   * one more click, and the fact that you can take some out is on screen rather
   * than hidden behind a Select button that says nothing about $ai.
   */
  const enterSelectMode = useCallback(
    (preselect = []) => {
      setAiLimitDialog(null)
      reorderSessionRef.current = null
      enterSelect(preselect)
    },
    [enterSelect],
  )

  const enterReorderMode = useCallback(() => {
    reorderSessionRef.current = {
      baseline: [...customs],
      dirty: false,
      failed: false,
      save: Promise.resolve(),
    }
    enterReorder()
  }, [customs, enterReorder])

  /** The file picker behind both "Add image" buttons — toolbar and empty state. */
  const openCustomFilePicker = useCallback(() => customInputRef.current?.click(), [])

  const exitReorderMode = useCallback(() => {
    reorderSessionRef.current = null
    resetSelection()
  }, [resetSelection])

  /**
   * Put the order back the way it was when the session opened.
   *
   * The baseline is a snapshot, so writing it back verbatim would re-assert
   * positions for images that have since been removed and would say nothing
   * about images added since. Reconciling it against what is actually here
   * keeps the request describing the gallery in front of the person, rather
   * than the one they opened twenty minutes ago.
   */
  const discardReorder = useCallback(async () => {
    const session = reorderSessionRef.current
    exitReorderMode()
    if (!session?.dirty) return
    const { baseline } = session
    try {
      await session.save
      const present = new Set(allRows.map((row) => row.url))
      const inBaseline = new Set(baseline)
      const order = [
        ...baseline.filter((url) => present.has(url)),
        ...allRows.map((row) => row.url).filter((url) => !inBaseline.has(url)),
      ]
      await apiClient.reorderCustomImages(name, order)
      applyOrderToCache(queryClient, name, order)
      addToast('Order reverted to before you started reordering.', 'info')
    } catch (e) {
      addToast(e.message || 'Could not revert order', 'error')
      await refreshImages()
    }
  }, [allRows, exitReorderMode, name, queryClient, refreshImages, addToast])

  /**
   * Leaving reorder mode by the Discard button.
   *
   * Discarding is a server write that throws away everything the session did,
   * and it sat one click away with nothing in between. Having moved nothing,
   * though, there is nothing to confirm and nothing to write, so that case
   * stays a plain exit.
   */
  const cancelReorder = useCallback(() => {
    if (!reorderSessionRef.current?.dirty) {
      exitReorderMode()
      return
    }
    askDiscard()
  }, [exitReorderMode, askDiscard])

  const doneReorder = useCallback(async () => {
    const session = reorderSessionRef.current
    exitReorderMode()
    if (!session?.dirty) return
    // One confirmation for the whole session. A toast per drop meant a dozen
    // identical undo-less toasts stacked over the gallery being edited, which
    // is how people learn to dismiss toasts without reading them.
    await session.save
    if (!session.failed) addToast('New order saved', 'success')
  }, [exitReorderMode, addToast])

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

  const upload = useCustomImageUpload({
    characterName: name,
    // The upload hands back the new URLs; the gallery refetches rather than
    // appending them, because Hide and Report need the server-assigned row ids.
    onUploaded: refreshImages,
    addToast,
    fileInputRef: customInputRef,
  })

  const reorder = useGalleryReorder({
    items: customs,
    enabled: reorderMode,
    indicesFor: getIndicesToMove,
    onReorder: (next) => applyReorder(next),
  })

  /**
   * The main portrait, its own hook: replace by file, drop, or Mudae refresh.
   * The sign-in check lives inside it, before anything is read or sent.
   */
  const main = useMainImage({
    name,
    canAddImages,
    onChanged: setMainImage,
    addToast,
    onMudaeRefresh: async () => {
      addToast('Fetching main image from Mudae…', 'info')
      const res = await apiClient.mudaeRefreshMainImage(name)
      setMainImage(res.image_url)
      reloadChar()
      addToast(res.message || 'Main image updated from Mudae', 'success')
    },
  })

  const applyReorder = useCallback(
    (newOrder) => {
      // The gallery renders from the query cache, so writing the order there is
      // what makes the drop land. It used to wait for a refetch of the whole
      // character before the image appeared in its new place.
      applyOrderToCache(queryClient, name, newOrder)
      const session = reorderSessionRef.current
      if (!session) return
      session.dirty = true
      session.save = session.save
        .then(() => apiClient.reorderCustomImages(name, newOrder))
        .catch(async (err) => {
          // Say so once, then show what the server actually holds: the gallery
          // is now displaying an order that was never saved.
          if (!session.failed) addToast(err.message || 'Could not save the new order', 'error')
          session.failed = true
          await refreshImages()
        })
    },
    [name, queryClient, refreshImages, addToast],
  )

  // Three states, not two. `char` is absent both while the record is being
  // fetched and when the character genuinely does not exist, and conflating them
  // meant every shared link opened on an error.
  if (!char && charLoading) return <CharacterLoadingState />
  if (!char) {
    return (
      <Card as="section" padding="lg">
        <h1 className="page-title">Character not found</h1>
        <EmptyState
          title={`Nothing here called "${name}"`}
          description="It may have been renamed, or the link may be wrong."
          action={
            <Button as={Link} to="/">
              Back to search
            </Button>
          }
        />
      </Card>
    )
  }

  const handleSaveEdit = async () => {
    setLoading(true)
    try {
      await apiClient.editCharacter({
        original_name: name,
        new_name: editName,
        series: editSeries,
        rank: editRank,
        ...keysToTraits(editTraits),
      })
      await queryClient.invalidateQueries({ queryKey: savedKey })
      reloadChar()
      if (name !== editName) {
        // The rows are keyed by name, so the renamed character fetches under
        // its new key. Drop the old entry rather than leaving a stale gallery
        // behind the old name.
        queryClient.removeQueries({ queryKey: characterImagesKey(name) })
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
        await removeSaved.mutateAsync(name)
        addToast('Removed from saved', 'success')
      } else {
        await saveCharacter.mutateAsync(char)
        addToast('Saved character', 'success')
      }
    } catch (err) {
      addToast(err.message, 'error')
    }
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
  /** Every image here you added, selected or not — what "Select mine" reaches. */
  const mineCount = rows.filter((row) => row.is_mine).length
  const othersSelected = selectedRows.filter((row) => !row.is_mine)

  /**
   * This viewer's own `$ai` copy history for this character, for the
   * "already used" selection helpers. `ever` is every image they have copied
   * here; `last` is only their most recent copy. Both are scoped to them, so
   * this is a memory aid and never a signal about anyone else.
   *
   * "Last batch" is empty for history that predates batch ids, in which case
   * the switch would offer a scope that selects nothing — so the helpers fall
   * back to the ever set and the last-batch option is dropped below.
   */
  const copiedIds = imagesData?.copiedIds ?? []
  const lastBatchIds = imagesData?.lastBatchIds ?? []
  const hasLastBatch = lastBatchIds.length > 0
  const scopeIds = copiedScope === 'last' && hasLastBatch ? lastBatchIds : copiedIds
  const copiedSet = new Set(scopeIds)
  // Counts are over the gallery as shown, so a hidden image is neither offered
  // nor counted by a helper that selects from what you can see.
  const copiedCount = rows.filter((row) => copiedSet.has(row.id)).length
  const uncopiedCount = rows.length - copiedCount

  const removeOwnImages = async () => {
    setConfirmRemove(null)
    const urls = mineSelected.map((row) => row.url)
    if (!urls.length) return
    try {
      const result = await apiClient.deleteCustomImages(name, urls)
      await refreshImages()
      const removed = result?.removed?.length ?? urls.length
      addToast(`${removed} image${removed === 1 ? '' : 's'} removed`, 'success', {
        onUndo: async () => {
          // Restore, not reorder. The old undo wrote a stale array back through
          // reorderCustomImages, which clobbered anyone else's concurrent edits
          // and could not bring a removed image back at all.
          await apiClient.restoreImages(name, urls)
          await refreshImages()
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
      await refreshImages()
      addToast(`${ids.length} image${ids.length === 1 ? '' : 's'} hidden for you`, 'success', {
        onUndo: async () => {
          await apiClient.unhideImages(ids)
          await refreshImages()
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
      await refreshImages()
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

  const handleReport = async (imageId, reason) => {
    setReportTarget(null)
    try {
      const result = await apiClient.reportImage(imageId, reason)
      await refreshImages()
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
    if (mode !== 'browse') {
      toggleUrl(url)
    }
  }

  const selectAllImages = () => {
    setSelection([...customs])
  }

  /**
   * Select every image you added.
   *
   * Removing your own images used to mean entering a mode that tagged all 256
   * thumbnails with who added them and reading the gallery for the handful that
   * said "Yours". The set is already known here, so it can simply be handed
   * over.
   */
  const selectMineImages = () => {
    setSelection(rows.filter((row) => row.is_mine).map((row) => row.url))
  }

  /**
   * Select the images this viewer has, or has not, already copied into an $ai
   * command — the third half of the problem PRODUCT.md describes ("remembering
   * which ones are already in use"). Selecting is not capped here: only the
   * `$ai` command cares about Mudae's 100, and remove/hide/download act on a
   * selection of any size.
   */
  const selectCopiedImages = () => {
    setSelection(rows.filter((row) => copiedSet.has(row.id)).map((row) => row.url))
  }

  const selectUncopiedImages = () => {
    setSelection(rows.filter((row) => !copiedSet.has(row.id)).map((row) => row.url))
  }

  /**
   * Build the $ai command for `urls`.
   *
   * Takes them rather than reading the selection, because it serves two callers
   * that mean different things: the header copies the command for the whole
   * character in one click, and the toolbar copies one for the images you
   * picked. It used to read `selectedUrls.length ? selectedUrls : customs`,
   * which made the same button mean either depending on invisible state.
   */
  const generateAiCommand = (urls) => {
    if (!urls.length) return
    const charName = editMode ? editName : char.name
    // Mudae caps a character at 100 custom images via `$ai`; anything more is
    // rejected. Take the first 100 in gallery order and say how many were
    // dropped, rather than handing over a command the bot will refuse.
    const { urls: capped, dropped } = capAiImages(urls)
    // Recorded on this first click, before any Discord length split: the batch
    // is everything the user chose at this moment, and the split into several
    // pastes is a delivery detail, not several intents. A batch is therefore
    // written even if they then close the length dialog without copying.
    recordTakes(capped, 'copy_command')
    const cmd = buildAiCommand(charName, capped)
    const noteDropped = () => {
      if (dropped > 0) {
        addToast(`Mudae allows 100 images per character — the first 100 were copied.`, 'info')
      }
    }
    if (cmd.length < DISCORD_LIMIT_REGULAR) {
      navigator.clipboard
        .writeText(cmd)
        .then(() => {
          addToast('Command copied to clipboard', 'success')
          noteDropped()
          resetModes()
        })
        .catch(() => addToast('Failed to copy', 'error'))
      return
    }
    const nonNitroParts = splitAiCommandForLimit(charName, capped, DISCORD_LIMIT_REGULAR)
    const nitroParts =
      cmd.length <= DISCORD_LIMIT_NITRO
        ? [cmd]
        : splitAiCommandForLimit(charName, capped, DISCORD_LIMIT_NITRO)
    setAiLimitDialog({
      charCount: cmd.length,
      nonNitroParts,
      nitroParts,
      dropped,
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

  /** Modal viewer: custom images only (main portrait is separate above the gallery) */
  const galleryModalImages = customs.map((u) => getImageUrl(u) || u).filter(Boolean)

  return (
    <Card
      as="article"
      padding="lg"
      className={`character-page${mode === 'browse' ? '' : ' has-action-bar'}`}
    >
      <CharacterHeader
        char={char}
        mainImage={mainImage}
        mainThumb={mainThumb}
        mainInputRef={mainInputRef}
        loading={loading}
        dragOver={main.dragOver}
        onDragOverChange={main.setDragOver}
        onMainImageChange={main.onFileInputChange}
        onMainImageDrop={main.onDrop}
        canAddImages={canAddImages}
        isSaved={isSaved}
        onToggleSave={handleToggleSave}
        onGetAiCommand={() => enterSelectMode([...customs])}
        customCount={customs.length}
        edit={{
          active: editMode,
          name: editName,
          series: editSeries,
          rank: editRank,
          setName: setEditName,
          setSeries: setEditSeries,
          setRank: setEditRank,
          traits: editTraits,
          toggleTrait: toggleEditTrait,
          start: () => setEditMode(true),
          cancel: () => setEditMode(false),
          save: handleSaveEdit,
        }}
        mudae={{
          configured: mudaeConfigured,
          busy: main.mudaeBusy,
          onRefreshMain: main.refreshFromMudae,
        }}
        pick={accent.pick}
        onPickPortrait={accent.pickFromPortrait}
        accent={{
          canEdit: Boolean(me?.is_moderator),
          manual: Boolean(imagesData?.accentManual),
          pickMode: accent.pick,
          busy: accent.busy,
          seed: seededAccent,
          onTogglePick: accent.togglePick,
          onClear: accent.clear,
        }}
      />

      {/*
        A drop target for files and for images dragged in from a web page. There
        is no keyboard gesture for "drop a file", so nothing here is withheld
        from a keyboard user: the toolbar's "Add Image" button reaches the same
        upload path and is the accessible route to it.
      */}
      {/* biome-ignore lint/a11y/noStaticElementInteractions: file drop zone, see above */}
      <div
        className={`custom-images-section ${upload.dragOver ? 'drag-over' : ''}`}
        onDragOver={canAddImages ? upload.onDragOver : (e) => e.preventDefault()}
        onDragLeave={canAddImages ? upload.onDragLeave : undefined}
        onDrop={
          canAddImages
            ? upload.onDrop
            : (e) => {
                e.preventDefault()
                addToast('Sign in with Discord to add images', 'error')
              }
        }
      >
        <div className="custom-images-header-row">
          <h2 className="section-heading custom-images-heading">
            Custom Images
            {/* The count belongs on a page whose premise is "up to 256 of
                these". The class already existed and nothing rendered it. */}
            {customs.length > 0 && (
              <span className="toolbar-selection-count">{customs.length}</span>
            )}
            {/*
              The mode travels with the content it governs. It used to be
              signalled only by which buttons happened to be rendered, in a
              toolbar that scrolls out of sight on a long gallery -- so on a
              256-image character the only way to discover you were in remove
              mode was to click an image and watch it be selected rather than
              opened. role="status" announces the change rather than leaving a
              screen reader to find it by re-reading an item's label.
            */}
            {MODE_LABELS[mode] && (
              <span className="custom-images-mode" role="status">
                {MODE_LABELS[mode]}
              </span>
            )}
          </h2>
          {/* Browse only. Everything an open mode needs is in the bar fixed to
              the bottom of the viewport, within reach of wherever you have
              scrolled to. */}
          {mode === 'browse' && (
            <div className="char-custom-toolbar">
              <GalleryToolbar
                totalCount={customs.length}
                hiddenCount={hiddenCount}
                showHidden={showHidden}
                uploadBusy={!!upload.progress}
                onEnterSelect={() => enterSelectMode()}
                onEnterReorder={enterReorderMode}
                onUnhideAll={handleUnhideAll}
                onToggleShowHidden={() => setShowHidden((v) => !v)}
                onOpenRemovedDrawer={openRemovedDrawer}
                onAddImage={openCustomFilePicker}
                canAddImages={canAddImages}
                canReorder={Boolean(me?.signed_in)}
              />
            </div>
          )}
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
                <strong>Keyboard:</strong> tab to an image and use the <strong>arrow keys</strong>{' '}
                to move it. Each move is announced.
              </p>
              <p>
                <strong>Move several at once:</strong> tap images to select them (or Clear
                selection), then drag any selected image — or use the arrow keys. The whole group
                moves together.
              </p>
              <p>
                <strong>Saving:</strong> every move is saved as you make it. Done simply closes
                reorder mode; <strong>Discard changes</strong> puts the order back the way it was
                when you opened it.
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
          onChange={upload.onFileInputChange}
          disabled={!!upload.progress}
        />
        {upload.progress && (
          <div className="custom-upload-progress" role="status" aria-live="polite">
            <span className="custom-upload-progress-spinner" aria-hidden />
            <span className="custom-upload-progress-text">
              {upload.progress.phase === 'starting'
                ? `Preparing ${upload.progress.total} image${upload.progress.total !== 1 ? 's' : ''}…`
                : `Uploading ${upload.progress.current}/${upload.progress.total}${upload.progress.fileName ? ` — ${upload.progress.fileName}` : ''}`}
            </span>
          </div>
        )}
        <CustomImageGallery
          rows={rows}
          ratios={ratios}
          loading={galleryLoading}
          modes={{ select: selectMode, reorder: reorderMode }}
          selectedUrls={selectedUrls}
          reorder={reorder}
          onToggleSelect={toggleSelect}
          onOpenImage={openModal}
          onImageLoad={noteRatio}
          onDragOver={onGalleryDragOver}
          pick={accent.pick}
          onPick={accent.pickFromGallery}
          /*
            An empty gallery used to be a blank strip under the drop hint, which
            reads as something that failed to load rather than a character
            nobody has added an image to yet. Hidden images make that worse:
            hiding the last one emptied the gallery with no sign that the images
            still exist and are one button away.
          */
          empty={
            hiddenCount > 0 && !showHidden ? (
              <EmptyState
                className="gallery-empty"
                title={
                  hiddenCount === 1
                    ? 'The only image here is one you hid'
                    : `All ${hiddenCount} images here are ones you hid`
                }
                description="Hiding is per person, so this is only how the page looks to you."
                action={
                  <Button size="sm" onClick={() => setShowHidden(true)}>
                    Show them
                  </Button>
                }
              />
            ) : (
              <EmptyState
                className="gallery-empty"
                title="No custom images yet"
                description={
                  !canAddImages
                    ? `Adding images needs a linked Discord account. Once signed in, an image becomes part of the $ai command for ${name}.`
                    : isNarrow
                      ? `Add one and it becomes part of the $ai command for ${name}.`
                      : `Add one — drop a file or an image from the web here, or use the button — and it becomes part of the $ai command for ${name}.`
                }
                action={
                  canAddImages ? (
                    <Button size="sm" disabled={!!upload.progress} onClick={openCustomFilePicker}>
                      Add image
                    </Button>
                  ) : (
                    <SignInPrompt />
                  )
                }
              />
            )
          }
        />
      </div>

      {mode !== 'browse' && (
        <GallerySelectionBar
          mode={mode}
          selectedCount={selectedUrls.length}
          totalCount={customs.length}
          mineCount={mineCount}
          mineSelectedCount={mineSelected.length}
          othersSelectedCount={othersSelected.length}
          onSelectAll={selectAllImages}
          onSelectMine={selectMineImages}
          copiedCount={copiedCount}
          uncopiedCount={uncopiedCount}
          copiedScope={hasLastBatch ? copiedScope : 'ever'}
          lastBatchAvailable={hasLastBatch}
          onCopiedScopeChange={setCopiedScope}
          onSelectCopied={selectCopiedImages}
          onSelectUncopied={selectUncopiedImages}
          onClearSelection={() => setSelection([])}
          onGenerateAiCommand={() => generateAiCommand(selectedUrls)}
          onDownloadSelected={handleDownloadSelected}
          onRemoveSelected={handleRemoveSelected}
          onHideSelected={handleHideSelected}
          onExitMode={resetModes}
          onCancelReorder={cancelReorder}
          onDoneReorder={doneReorder}
        />
      )}

      {modalOpen && (
        <ImageModal
          images={galleryModalImages}
          currentIndex={modalIndex}
          onClose={closeModal}
          onPrev={prevImage}
          onNext={nextImage}
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
      {confirmDiscardOrder && (
        <ConfirmDialog
          title="Discard the new order?"
          body={
            <>
              Every move you made in this session goes back to the order you started with. Images
              added or removed while you were reordering stay where they are.
            </>
          }
          confirmLabel="Discard"
          variant="danger"
          onConfirm={discardReorder}
          onCancel={cancelDiscard}
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
            await refreshImages()
            addToast('Image restored', 'success')
          }}
          onClose={() => setRemovedDrawer(null)}
        />
      )}
      {upload.errorReport && (
        <UploadErrorDialog
          title="Upload issue"
          body={upload.errorReport}
          onClose={upload.dismissErrorReport}
        />
      )}
      {upload.duplicates && (
        <DuplicateDialog
          items={upload.duplicates.items}
          onSkip={upload.dismissDuplicates}
          onUploadAnyway={upload.uploadDuplicatesAnyway}
          onRestore={async (existing) => {
            try {
              await apiClient.restoreImages(existing.character, [existing.url])
              await refreshImages()
              addToast('Image restored', 'success')
              upload.resolveDuplicate(existing.id)
            } catch (err) {
              addToast(err.message || 'Could not restore that image', 'error')
            }
          }}
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

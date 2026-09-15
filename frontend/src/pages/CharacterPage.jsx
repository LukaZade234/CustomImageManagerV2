import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import AiCommandLimitDialog from '../components/AiCommandLimitDialog'
import { CharacterHeader } from '../components/CharacterHeader'
import CharacterLoadingState from '../components/CharacterLoadingState'
import CustomImageGallery from '../components/CustomImageGallery'
import { GallerySelectionBar } from '../components/GallerySelectionBar'
import { GalleryToolbar } from '../components/GalleryToolbar'
import ImageModal from '../components/ImageModal'
import RemovedDrawer from '../components/RemovedDrawer'
import ReportDialog from '../components/ReportDialog'
import UploadErrorDialog from '../components/UploadErrorDialog'
import { Button, Card, ConfirmDialog, EmptyState } from '../components/ui'
import { useApplyCharacterTheme } from '../hooks/useApplyCharacterTheme'
import { useCharacterTheme } from '../hooks/useCharacterTheme'
import { useCustomImageUpload } from '../hooks/useCustomImageUpload'
import { useGalleryReorder } from '../hooks/useGalleryReorder'
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
  DISCORD_LIMIT_NITRO,
  DISCORD_LIMIT_REGULAR,
  splitAiCommandForLimit,
} from '../utils/aiCommandDiscord'
import { keysToTraits, traitsToKeys } from '../utils/characterTraits'
import {
  downloadCustomImagesViaBrowser,
  writeCustomImagesToDirectory,
} from '../utils/downloadCustomImages'
import { ratioOf } from '../utils/galleryRatios'
import { isImageFileLike } from '../utils/imageFiles'
import { pickPixel } from '../utils/imagePick'

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
  // The four editable pool facets (waifu/husbando/anime/game). Seeded from the
  // row's stored card traits, so the editor shows exactly what the identity
  // block beside it shows.
  const [editTraits, setEditTraits] = useState([])
  const toggleEditTrait = (key) =>
    setEditTraits((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]))
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
  const [loading, setLoading] = useState(false)
  const [mudaeMainBusy, setMudaeMainBusy] = useState(false)
  const [mudaeConfigured, setMudaeConfigured] = useState(false)
  /**
   * The gallery is in exactly one mode at a time. Four independent booleans made
   * eleven of the sixteen combinations nonsense and needed twelve hand-written
   * "turn the others off" lines to stay consistent; one value cannot be wrong.
   */
  const [mode, setMode] = useState('browse')
  const selectMode = mode === 'select'
  const reorderMode = mode === 'reorder'
  // Arming the accent picker turns the portrait and gallery into a pixel
  // sampler: the next click sets the character's colour (staff only).
  const [accentPick, setAccentPick] = useState(false)
  const [accentBusy, setAccentBusy] = useState(false)
  const [aiLimitDialog, setAiLimitDialog] = useState(null)
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
  const [confirmDiscardOrder, setConfirmDiscardOrder] = useState(false)

  // Measure image ratios off the onLoad event, which fires once per image in
  // its own tick — a 256-image gallery meant 256 full re-renders of the grid
  // while it filled in. Coalescing a frame's worth of measurements into one
  // state update makes the fill cost one render per frame instead.
  const pendingRatiosRef = useRef({})
  const ratioFrameRef = useRef(0)
  useEffect(() => () => cancelAnimationFrame(ratioFrameRef.current), [])

  useEffect(() => {
    if (char) {
      setEditName(char.name)
      setEditSeries(char.series || '')
      setEditRank(char.rank || '')
      setMainImage(char.image || '')
      setEditTraits(traitsToKeys(char.is_female, char.is_male, char.pools))
    }
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
    setMode('browse')
    setSelectedUrls([])
    setAiLimitDialog(null)
    reorderSessionRef.current = null
  }, [])

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
      resetModes()
      setSelectedUrls(preselect)
      setMode('select')
    },
    [resetModes],
  )

  const enterReorderMode = useCallback(() => {
    setSelectedUrls([])
    reorderSessionRef.current = {
      baseline: [...customs],
      dirty: false,
      failed: false,
      save: Promise.resolve(),
    }
    setMode('reorder')
  }, [customs])

  /** The file picker behind both "Add image" buttons — toolbar and empty state. */
  const openCustomFilePicker = useCallback(() => customInputRef.current?.click(), [])

  const exitReorderMode = useCallback(() => {
    reorderSessionRef.current = null
    setConfirmDiscardOrder(false)
    setMode('browse')
    setSelectedUrls([])
  }, [])

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
    setConfirmDiscardOrder(true)
  }, [exitReorderMode])

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

  /**
   * Set or clear the character's accent from a picked pixel. The server samples
   * the image (keyed by row id, never a caller URL), so the click only has to
   * carry the point within the image.
   */
  const handlePickAccent = async (payload) => {
    setAccentBusy(true)
    try {
      const res = await apiClient.setAccentOverride({ name, ...payload })
      addToast(res.manual ? 'Accent colour saved' : 'Accent reset to measured', 'success')
      setAccentPick(false)
      await queryClient.invalidateQueries({ queryKey: characterImagesKey(name) })
      await queryClient.invalidateQueries({ queryKey: savedKey })
      reloadChar()
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setAccentBusy(false)
    }
  }

  const handlePickAccentFromGallery = (row, point) => {
    if (!row.thumb) {
      addToast('That image has no thumbnail to sample', 'error')
      return
    }
    handlePickAccent({ image_id: row.id, u: point.u, v: point.v })
  }

  const handlePickAccentFromPortrait = (e) => {
    const img = e.currentTarget.querySelector('img')
    const point = pickPixel(img, e.clientX, e.clientY)
    handlePickAccent({ portrait: true, u: point.u, v: point.v })
  }

  const handleClearAccent = () => handlePickAccent({ clear: true })

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
      reloadChar()
      addToast(res.message || 'Main image updated from Mudae', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setMudaeMainBusy(false)
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

  const noteRatio = (imageId, element) => {
    const ratio = ratioOf(element)
    if (ratio === null) return
    pendingRatiosRef.current[imageId] = ratio
    if (ratioFrameRef.current) return
    ratioFrameRef.current = requestAnimationFrame(() => {
      ratioFrameRef.current = 0
      const pending = pendingRatiosRef.current
      pendingRatiosRef.current = {}
      setRatios((prev) => {
        let changed = false
        const next = { ...prev }
        for (const [id, measured] of Object.entries(pending)) {
          if (next[id] !== measured) {
            next[id] = measured
            changed = true
          }
        }
        return changed ? next : prev
      })
    })
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
      setSelectedUrls((prev) =>
        prev.includes(url) ? prev.filter((u) => u !== url) : [...prev, url],
      )
    }
  }

  const selectAllImages = () => {
    setSelectedUrls([...customs])
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
    setSelectedUrls(rows.filter((row) => row.is_mine).map((row) => row.url))
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
    if (mode !== 'browse') return
    setModalIndex(index)
    setModalOpen(true)
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
        dragOver={dragOver}
        onDragOverChange={setDragOver}
        onMainImageChange={handleMainImageChange}
        onMainImageDrop={handleMainImageDrop}
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
          busy: mudaeMainBusy,
          onRefreshMain: handleMudaeRefreshMain,
        }}
        pick={accentPick}
        onPickPortrait={handlePickAccentFromPortrait}
        accent={{
          canEdit: Boolean(me?.is_moderator),
          manual: Boolean(imagesData?.accentManual),
          pickMode: accentPick,
          busy: accentBusy,
          seed: seededAccent,
          onTogglePick: () => setAccentPick((on) => !on),
          onClear: handleClearAccent,
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
        onDragOver={upload.onDragOver}
        onDragLeave={upload.onDragLeave}
        onDrop={upload.onDrop}
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
          pick={accentPick}
          onPick={handlePickAccentFromGallery}
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
                  isNarrow
                    ? `Add one and it becomes part of the $ai command for ${name}.`
                    : `Add one — drop a file or an image from the web here, or use the button — and it becomes part of the $ai command for ${name}.`
                }
                action={
                  <Button size="sm" disabled={!!upload.progress} onClick={openCustomFilePicker}>
                    Add image
                  </Button>
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
          onClearSelection={() => setSelectedUrls([])}
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
          onCancel={() => setConfirmDiscardOrder(false)}
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

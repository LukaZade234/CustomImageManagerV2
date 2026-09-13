import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import SeriesSuggestInput from '../components/SeriesSuggestInput'
import { Button, Card, Field, Input } from '../components/ui'
import { useCatalogMatch, useCatalogSuggest } from '../hooks/useCatalogSuggest'
import { useStore } from '../store/useStore'

/** Discord/CDN images often fail as bare <img src>; preview via backend proxy.
 *  mudae.net portraits are hotlink-friendly (the app sends no Referer) and are
 *  served directly rather than through the proxy. */
function mudaePreviewSrc(imageUrl) {
  if (!imageUrl) return ''
  let url = imageUrl
  if (url.startsWith('//')) url = `https:${url}`
  if (url.startsWith('http://') || url.startsWith('https://')) {
    try {
      const host = new URL(url).hostname.toLowerCase()
      if (host === 'mudae.net' || host.endsWith('.mudae.net')) return url
    } catch {
      /* fall through to the proxy */
    }
    return `/api/mudae/proxy-image?url=${encodeURIComponent(url)}`
  }
  return getImageUrl(url)
}

/** Case/space-insensitive comparison, matching the backend's folded name key. */
function normalizeSeries(value) {
  return (value || '').normalize('NFKC').replace(/\s+/g, ' ').trim().toLowerCase()
}

function mudaeCandidatesFromResponse(res) {
  if (Array.isArray(res?.candidate_matches) && res.candidate_matches.length) {
    return res.candidate_matches.map((m) => ({
      name: m.name,
      label: m.label || (m.series ? `${m.name} - ${m.series}` : m.name),
    }))
  }
  return (res?.candidates || []).map((n) => ({ name: n, label: n }))
}

export default function AddPage() {
  const [name, setName] = useState('')
  const [series, setSeries] = useState('')
  const [rank, setRank] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)

  const [mudaeConfigured, setMudaeConfigured] = useState(null)
  const [mudaeLookupName, setMudaeLookupName] = useState('')
  const [mudaeBusy, setMudaeBusy] = useState(false)
  const [mudaePreview, setMudaePreview] = useState(null)
  const [mudaeCandidates, setMudaeCandidates] = useState([])
  const [seriesBulkName, setSeriesBulkName] = useState('')
  const [seriesCandidates, setSeriesCandidates] = useState([])
  const [seriesResolving, setSeriesResolving] = useState(false)
  const [seriesBusy, setSeriesBusy] = useState(false)
  const [seriesCancelling, setSeriesCancelling] = useState(false)
  const [seriesResult, setSeriesResult] = useState(null)
  const [seriesProgress, setSeriesProgress] = useState(null)
  // Once the series field is edited or chosen, the library's suggestion stops
  // overwriting it -- the mismatch check is what speaks after that.
  const [seriesTouched, setSeriesTouched] = useState(false)

  const navigate = useNavigate()
  const loadCharacters = useStore((s) => s.loadCharacters)
  const addToast = useStore((s) => s.addToast)

  useEffect(() => {
    apiClient
      .mudaeStatus()
      .then((r) => setMudaeConfigured(!!r.configured))
      .catch(() => setMudaeConfigured(false))
  }, [])

  // Catalog-backed suggestions and the library's own record for the typed name.
  const nameSuggestions = useCatalogSuggest(name, { kind: 'characters', limit: 8 })
  const seriesSuggestions = useCatalogSuggest(series, { kind: 'series', limit: 20 })
  const panelNameSuggestions = useCatalogSuggest(mudaeLookupName, { kind: 'characters', limit: 8 })
  const bulkSeriesSuggestions = useCatalogSuggest(seriesBulkName, { kind: 'series', limit: 20 })
  const nameMatch = useCatalogMatch(name)

  const nameSuggestionItems = useMemo(
    () =>
      nameSuggestions.map((c) => ({
        value: c.name,
        label: c.name,
        meta: c.series || undefined,
        series: c.series || '',
      })),
    [nameSuggestions],
  )
  const panelNameItems = useMemo(
    () =>
      panelNameSuggestions.map((c) => ({
        value: c.name,
        label: c.name,
        meta: c.series || undefined,
      })),
    [panelNameSuggestions],
  )

  // The library knows this character's series: offer it when the field is empty
  // and still untouched, and flag it when a different one is typed.
  const seriesMismatch =
    Boolean(nameMatch?.series) &&
    Boolean(series.trim()) &&
    normalizeSeries(series) !== normalizeSeries(nameMatch.series)

  useEffect(() => {
    if (!nameMatch?.series || seriesTouched) return
    if (!series.trim() && series !== nameMatch.series) {
      setSeries(nameMatch.series)
    }
  }, [nameMatch, series, seriesTouched])

  const handlePickName = (item) => {
    if (item?.series) {
      setSeries(item.series)
      setSeriesTouched(true)
    }
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    if (seriesMismatch) {
      const message = `Series doesn't match — "${nameMatch.name}" is in "${nameMatch.series}".`
      setStatus({ type: 'error', message })
      addToast(message, 'error')
      return
    }
    setLoading(true)
    setStatus(null)
    try {
      const formData = new FormData()
      formData.append('name', name.trim())
      formData.append('series', series.trim())
      formData.append('rank', rank.trim())
      if (imageFile) formData.append('image', imageFile)
      await apiClient.addCharacter(formData)
      await loadCharacters()
      addToast(`Added "${name}"`, 'success')
      setName('')
      setSeries('')
      setRank('')
      setImageFile(null)
      setSeriesTouched(false)
      setTimeout(() => navigate(`/character/${encodeURIComponent(name.trim())}`), 500)
    } catch (err) {
      setStatus({ type: 'error', message: err.message })
      addToast(err.message, 'error')
    } finally {
      setLoading(false)
    }
  }

  const applyMudaeCharacter = (character) => {
    if (!character) return
    setName(character.name || '')
    setSeries(character.series || '')
    setSeriesTouched(true)
    setRank(character.rank || '')
    // Catalog results carry `image`; Mudae results carry `image_url`. Normalise
    // so the preview and the panel render either.
    setMudaePreview({
      ...character,
      image_url: character.image_url || character.image || '',
    })
    setMudaeCandidates([])
    setImageFile(null)
  }

  const handleMudaeLookup = async (queryName) => {
    const q = (queryName || mudaeLookupName || name).trim()
    if (!q) {
      addToast('Enter a character name to look up', 'error')
      return
    }
    setMudaeBusy(true)
    setMudaeCandidates([])
    setMudaePreview(null)
    setStatus(null)
    try {
      // Library first: a name the catalog already knows costs no Mudae request.
      const local = await apiClient.findCatalogCharacter(q)
      if (local.found) {
        applyMudaeCharacter(local.character)
        setMudaeLookupName(local.character.name || q)
        addToast(`Found "${local.character.name}" in the library`, 'success')
        return
      }
      if (!mudaeConfigured) {
        addToast('Not in the library, and Mudae lookup is not available', 'error')
        return
      }
      const res = await apiClient.mudaeLookupCharacter(q, false)
      if (res.type === 'candidates') {
        const matches = mudaeCandidatesFromResponse(res)
        if (!matches.length) {
          addToast('Mudae returned matches but none could be parsed', 'error')
          return
        }
        setMudaeCandidates(matches)
        addToast(`Multiple matches — pick one (${matches.length})`, 'info')
        return
      }
      if (res.character) {
        applyMudaeCharacter(res.character)
        setMudaeLookupName(res.character.name || q)
        addToast(`Found "${res.character.name}" from Mudae`, 'success')
      } else {
        addToast('No character found in Mudae', 'error')
      }
    } catch (err) {
      addToast(err.message, 'error')
      setStatus({ type: 'error', message: err.message })
    } finally {
      setMudaeBusy(false)
    }
  }

  const handleMudaeAdd = async () => {
    const q = (mudaePreview?.name || mudaeLookupName || name).trim()
    if (!q) {
      addToast('Enter a character name', 'error')
      return
    }
    setMudaeBusy(true)
    setStatus(null)
    try {
      // Catalog first: adding a known character needs no Discord and no ImgChest.
      const local = await apiClient.findCatalogCharacter(q)
      if (local.found) {
        if (local.character.in_library) {
          const message = `Character "${local.character.name}" already exists`
          addToast(message, 'error')
          setStatus({ type: 'error', message })
          return
        }
        const res = await apiClient.catalogAddCharacter(local.character.name)
        const addedName = res.character?.name || local.character.name
        await loadCharacters()
        addToast(res.message || `Added "${addedName}"`, 'success')
        setMudaePreview(null)
        setMudaeCandidates([])
        setMudaeLookupName('')
        setTimeout(() => navigate(`/character/${encodeURIComponent(addedName)}`), 500)
        return
      }
      if (!mudaeConfigured) {
        addToast('Not in the library, and Mudae is not available', 'error')
        return
      }
      const res = await apiClient.mudaeLookupCharacter(q, true)
      if (res.type === 'candidates') {
        const matches = mudaeCandidatesFromResponse(res)
        setMudaeCandidates(matches)
        addToast('Multiple matches — pick one, then add again', 'info')
        return
      }
      const addedName = res.character?.name || q
      await loadCharacters()
      addToast(res.message || `Added "${addedName}"`, 'success')
      setMudaePreview(null)
      setMudaeCandidates([])
      setMudaeLookupName('')
      setTimeout(() => navigate(`/character/${encodeURIComponent(addedName)}`), 500)
    } catch (err) {
      addToast(err.message, 'error')
      setStatus({ type: 'error', message: err.message })
    } finally {
      setMudaeBusy(false)
    }
  }

  const handleSeriesBulk = async (e) => {
    e.preventDefault()
    const s = seriesBulkName.trim()
    if (!s) return
    setSeriesCandidates([])
    setSeriesResolving(true)
    setSeriesResult(null)
    let importName = null
    try {
      const resolved = await apiClient.mudaeLookupSeries(s)
      if (resolved.type === 'candidates') {
        const matches = mudaeCandidatesFromResponse(resolved)
        if (!matches.length) {
          addToast('Mudae returned matches but none could be parsed', 'error')
          return
        }
        setSeriesCandidates(matches)
        addToast(`Multiple series matches — pick one (${matches.length})`, 'info')
        return
      }
      importName = resolved.series_label || s
      setSeriesBulkName(importName)
    } catch (err) {
      addToast(err.message, 'error')
      setSeriesResult({ error: err.message })
    } finally {
      setSeriesResolving(false)
    }
    if (importName) {
      await runSeriesImport(importName)
    }
  }

  const runSeriesImport = async (seriesName) => {
    const s = (seriesName || seriesBulkName).trim()
    if (!s) return
    setSeriesBusy(true)
    setSeriesCancelling(false)
    setSeriesResult(null)
    setSeriesCandidates([])
    setSeriesProgress({
      phase: 'starting',
      series: s,
      totalListed: 0,
      current: null,
      added: [],
      failed: [],
      skipped: [],
    })
    addToast(`Fetching series "${s}" from Mudae — this can take a while…`, 'info')
    try {
      const res = await apiClient.mudaeAddSeriesStream(s, {
        ima_complete: (d) => {
          setSeriesProgress((p) => ({
            ...p,
            phase: 'delay',
            series: d.series || s,
            totalListed: d.total_listed || 0,
            current: null,
          }))
        },
        ima_delay_done: () => {
          setSeriesProgress((p) => ({ ...p, phase: 'adding' }))
        },
        lookup_start: (d) => {
          setSeriesProgress((p) => ({
            ...p,
            phase: d.retry ? 'retry' : 'adding',
            current: d.name,
          }))
        },
        added: (d) => {
          setSeriesProgress((p) => ({
            ...p,
            added: [...p.added, d],
            current: d.name,
          }))
        },
        skipped: (d) => {
          setSeriesProgress((p) => ({
            ...p,
            skipped: [...p.skipped, d.name],
          }))
        },
        failed: (d) => {
          setSeriesProgress((p) => ({
            ...p,
            failed: [...p.failed, d],
          }))
        },
        retry_pass_start: () => {
          setSeriesProgress((p) => ({ ...p, phase: 'retry' }))
        },
        cancelled: () => {
          setSeriesCancelling(true)
          setSeriesProgress((p) => (p ? { ...p, phase: 'cancelled' } : p))
        },
      })
      setSeriesResult(res)
      setSeriesProgress((p) => (p ? { ...p, phase: res?.cancelled ? 'cancelled' : 'done' } : p))
      if (res?.cancelled) {
        addToast(res?.message || 'Series import cancelled', 'info')
      } else {
        addToast(res?.message || 'Series import finished', 'success')
      }
    } catch (err) {
      if (err.candidateMatches?.length) {
        const matches = mudaeCandidatesFromResponse({ candidate_matches: err.candidateMatches })
        setSeriesCandidates(matches)
        addToast(`Multiple series matches — pick one (${matches.length})`, 'info')
        setSeriesResult(null)
      } else {
        addToast(err.message, 'error')
        setSeriesResult({ error: err.message })
      }
      setSeriesProgress((p) => (p ? { ...p, phase: 'error' } : p))
    } finally {
      setSeriesBusy(false)
      setSeriesCancelling(false)
      try {
        await loadCharacters()
      } catch {
        /* keep prior list if refresh fails */
      }
    }
  }

  const handlePickSeriesCandidate = (name) => {
    setSeriesBulkName(name)
    setSeriesCandidates([])
    runSeriesImport(name)
  }

  const handleCancelSeries = async () => {
    if (!seriesBusy || seriesCancelling) return
    setSeriesCancelling(true)
    try {
      await apiClient.mudaeCancelSeries()
      addToast('Stopping import after the current step…', 'info')
    } catch (err) {
      addToast(err.message, 'error')
      setSeriesCancelling(false)
    }
  }

  return (
    <Card as="section" padding="lg">
      <h1 className="page-title">Add New Character</h1>

      <div className="edit-form-container mudae-panel">
        <h3 className="section-heading">Look up a character</h3>
        <p className="mudae-note">
          Checks the library first, then Mudae <code>$im</code> if the name is not known. Adding a
          known character needs no Mudae request.
        </p>

        <div className="edit-group full-width">
          <label htmlFor="mudaeCharName">Character name</label>
          <div className="mudae-row">
            <SeriesSuggestInput
              id="mudaeCharName"
              className="modern-input"
              placeholder="e.g. Rem"
              value={mudaeLookupName}
              onChange={(e) => setMudaeLookupName(e.target.value)}
              suggestions={panelNameItems}
              ariaLabel="Character name suggestions"
              disabled={mudaeBusy}
            />
            <Button
              variant="secondary"
              disabled={mudaeBusy || !mudaeLookupName.trim()}
              onClick={() => handleMudaeLookup()}
            >
              {mudaeBusy ? 'Querying…' : 'Lookup'}
            </Button>
            <Button
              variant="primary"
              disabled={mudaeBusy || !(mudaePreview?.name || mudaeLookupName.trim())}
              onClick={handleMudaeAdd}
            >
              {mudaeBusy ? 'Working…' : 'Add'}
            </Button>
          </div>
        </div>

        {mudaeCandidates.length > 0 && (
          <div className="mudae-candidates">
            <div className="mudae-candidates__label">Pick a match:</div>
            <div className="mudae-chips">
              {mudaeCandidates.map((c) => (
                <Button
                  variant="secondary"
                  key={`${c.name}-${c.label}`}
                  disabled={mudaeBusy}
                  onClick={() => {
                    setMudaeLookupName(c.name)
                    handleMudaeLookup(c.name)
                  }}
                >
                  {c.label}
                </Button>
              ))}
            </div>
          </div>
        )}

        {mudaePreview && (
          <div className="mudae-preview">
            {mudaePreview.image_url && (
              <img
                src={mudaePreviewSrc(mudaePreview.image_url)}
                alt={mudaePreview.name}
                className="mudae-preview__img"
              />
            )}
            <div>
              <div>
                <strong>{mudaePreview.name}</strong>
              </div>
              <div className="mudae-preview__meta">{mudaePreview.series || '—'}</div>
              <div className="mudae-preview__meta">
                Claim rank: {mudaePreview.rank ? `#${mudaePreview.rank}` : '—'}
              </div>
              <p className="mudae-preview__hint">
                The manual form below was pre-filled, or use &quot;Add&quot; to save it to the
                library.
              </p>
            </div>
          </div>
        )}

        {mudaeConfigured && (
          <>
            <hr className="mudae-divider" />

            <form onSubmit={handleSeriesBulk}>
              <div className="edit-group full-width">
                <label htmlFor="mudaeSeriesBulk">Bulk-add series</label>
                <div className="mudae-row">
                  <SeriesSuggestInput
                    id="mudaeSeriesBulk"
                    placeholder="Exact series name"
                    value={seriesBulkName}
                    onChange={(e) => setSeriesBulkName(e.target.value)}
                    suggestions={bulkSeriesSuggestions}
                    disabled={seriesBusy || seriesResolving}
                  />
                  <Button
                    variant="primary"
                    type="submit"
                    disabled={seriesBusy || seriesResolving || !seriesBulkName.trim()}
                  >
                    {seriesResolving
                      ? 'Checking…'
                      : seriesBusy
                        ? 'Importing…'
                        : 'Add entire series'}
                  </Button>
                  {seriesBusy && (
                    <Button
                      variant="secondary"
                      disabled={seriesCancelling}
                      onClick={handleCancelSeries}
                    >
                      {seriesCancelling ? 'Cancelling…' : 'Cancel import'}
                    </Button>
                  )}
                </div>
                <p className="mudae-preview__hint">
                  Runs <code>$ima</code> then <code>$im</code> per character. Large series can take
                  several minutes; existing names are skipped.
                </p>
                {seriesCandidates.length > 0 && (
                  <div className="mudae-candidates">
                    <div className="mudae-candidates__label">Pick a series:</div>
                    <div className="mudae-chips">
                      {seriesCandidates.map((c) => (
                        <Button
                          variant="secondary"
                          key={`${c.name}-${c.label}`}
                          disabled={seriesBusy || seriesResolving}
                          onClick={() => handlePickSeriesCandidate(c.name)}
                        >
                          {c.label}
                        </Button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </form>

            {seriesProgress && seriesBusy && (
              <div className="mudae-progress">
                <div className="mudae-progress__label">
                  {seriesProgress.phase === 'starting' && 'Querying Mudae for series list…'}
                  {seriesProgress.phase === 'delay' && (
                    <>
                      Found {seriesProgress.totalListed} character
                      {seriesProgress.totalListed !== 1 ? 's' : ''} in &quot;{seriesProgress.series}
                      &quot; — waiting before lookups…
                    </>
                  )}
                  {seriesProgress.phase === 'adding' && seriesProgress.current && (
                    <>
                      Adding: <strong>{seriesProgress.current}</strong> (
                      {seriesProgress.added.length +
                        seriesProgress.skipped.length +
                        seriesProgress.failed.length}
                      {seriesProgress.totalListed ? ` / ${seriesProgress.totalListed}` : ''})
                    </>
                  )}
                  {seriesProgress.phase === 'retry' && 'Retrying failed characters…'}
                  {seriesProgress.phase === 'cancelled' && 'Stopping import…'}
                </div>
                {seriesProgress.added.length > 0 && (
                  <ul className="mudae-scroll-list">
                    {seriesProgress.added.map((c) => (
                      <li key={c.name} className="mudae-item--ok">
                        {c.name}
                      </li>
                    ))}
                  </ul>
                )}
                {seriesProgress.skipped.length > 0 && (
                  <details open>
                    <summary>
                      Skipped — already in library ({seriesProgress.skipped.length})
                    </summary>
                    <ul className="mudae-scroll-list">
                      {seriesProgress.skipped.map((name) => (
                        <li key={name} className="mudae-item--warn">
                          {name}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}

            {seriesResult && !seriesResult.error && !seriesBusy && (
              <div className="mudae-result">
                <div>{seriesResult.message}</div>
                {Array.isArray(seriesResult.added) && seriesResult.added.length > 0 && (
                  <details open={seriesResult.cancelled}>
                    <summary>Added ({seriesResult.added.length})</summary>
                    <ul>
                      {seriesResult.added.map((c) => (
                        <li key={c.name}>{c.name}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {Array.isArray(seriesResult.skipped) && seriesResult.skipped.length > 0 && (
                  <details>
                    <summary>Skipped — already in library ({seriesResult.skipped.length})</summary>
                    <ul>
                      {seriesResult.skipped.map((name) => (
                        <li key={name}>{name}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {Array.isArray(seriesResult.failed) && seriesResult.failed.length > 0 && (
                  <details>
                    <summary>Failed ({seriesResult.failed.length})</summary>
                    <ul>
                      {seriesResult.failed.map((f) => (
                        <li key={f.name}>
                          {f.name}: {f.error}
                        </li>
                      ))}
                    </ul>
                  </details>
                )}
              </div>
            )}
            {seriesResult?.error && <div className="form-error">{seriesResult.error}</div>}
          </>
        )}
        {!mudaeConfigured && (
          <p className="mudae-setup-hint">
            Bulk series import needs Mudae, which is not configured. Lookup and add still work from
            the library.
          </p>
        )}
      </div>

      <div className="edit-form-container add-char-panel">
        <h3 className="section-heading">Manual add</h3>
        <form onSubmit={handleSubmit} className="add-char-form">
          <Field label="Character Name" htmlFor="addCharName" className="full-width">
            <SeriesSuggestInput
              id="addCharName"
              className="ui-input"
              placeholder="e.g. Saber"
              value={name}
              onChange={(e) => setName(e.target.value)}
              suggestions={nameSuggestionItems}
              onPick={handlePickName}
              ariaLabel="Character name suggestions"
              ariaDescribedBy={status?.type === 'error' ? 'addCharStatus' : undefined}
              required
            />
          </Field>
          <div className="edit-group full-width">
            <label htmlFor="addCharSeries">Series</label>
            <SeriesSuggestInput
              id="addCharSeries"
              className="ui-input"
              placeholder="Series Name"
              value={series}
              onChange={(e) => {
                setSeries(e.target.value)
                setSeriesTouched(true)
              }}
              suggestions={seriesSuggestions}
              ariaLabel="Series suggestions"
              ariaInvalid={seriesMismatch}
            />
            {seriesMismatch && (
              <p className="form-error" role="alert">
                Series doesn&apos;t match — &quot;{nameMatch.name}&quot; is in &quot;
                {nameMatch.series}&quot;.
              </p>
            )}
          </div>
          <Field label="Rank (Optional)" htmlFor="addCharRank" className="full-width">
            <Input
              id="addCharRank"
              type="number"
              placeholder="Leave blank to skip"
              value={rank}
              onChange={(e) => setRank(e.target.value)}
            />
          </Field>
          <div className="edit-group full-width">
            <label htmlFor="addCharImage">Main Photo (Optional)</label>
            {/*
              A <label> for the file input rather than a div pretending to be a
              button. Clicking a label activates its control, so the picker opens
              with no JavaScript at all, and the input below is hidden with
              .sr-only rather than display:none -- which keeps it in the tab
              order, so the keyboard gets the same thing the mouse does.
            */}
            <label className="file-upload-box" htmlFor="addCharImage">
              <svg
                aria-hidden="true"
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                className="file-upload-icon"
              >
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <span id="addCharImageLabel" className="file-upload-hint">
                {imageFile ? imageFile.name : 'Click to select image (can be added later)'}
              </span>
              <input
                id="addCharImage"
                type="file"
                accept="image/*"
                className="sr-only"
                onChange={(e) => setImageFile(e.target.files?.[0] || null)}
              />
            </label>
          </div>
          <div className="edit-actions add-char-actions">
            <Button variant="primary" type="submit" disabled={loading}>
              {loading ? 'Adding...' : 'Add Character'}
            </Button>
          </div>
          {status?.type === 'error' && (
            <div id="addCharStatus" className="form-error" role="alert">
              {status.message}
            </div>
          )}
        </form>
      </div>
    </Card>
  )
}

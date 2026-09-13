import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import ExistingCharacterCard from '../components/ExistingCharacterCard'
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
  const [seriesBusy, setSeriesBusy] = useState(false)
  const [seriesPreview, setSeriesPreview] = useState(null)
  const [seriesApplying, setSeriesApplying] = useState(false)
  const [seriesApplyResult, setSeriesApplyResult] = useState(null)
  // The library fills the rank once the series is chosen, until the field is edited.
  const [rankTouched, setRankTouched] = useState(false)
  // A message shown inside the lookup panel, e.g. "already exists".
  const [mudaeError, setMudaeError] = useState(null)
  // The character a lookup found already in the library, shown as a clickable card.
  const [mudaeExisting, setMudaeExisting] = useState(null)

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
  // The name combobox gets the typed series as a hint, so a named series offers
  // its characters until the visitor starts typing a name of their own.
  const nameSuggestions = useCatalogSuggest(name, { kind: 'characters', limit: 8, series })
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

  // A name already in the working set cannot be added again. Otherwise, when the
  // name is a catalog entry and the series agrees, its portrait is offered too.
  // The match must be exact for the current text, so the moment the field
  // diverges the card and portrait vanish rather than lagging the debounce.
  const matchedExactly = Boolean(
    nameMatch && normalizeSeries(name) === normalizeSeries(nameMatch.name),
  )
  // For the manual form the series must match as well: a name that merely
  // coincides with another character's is not enough to offer that character.
  const seriesMatchesKnown = Boolean(
    matchedExactly &&
      nameMatch?.series &&
      normalizeSeries(series) === normalizeSeries(nameMatch.series),
  )
  const duplicateName = matchedExactly && Boolean(nameMatch.in_library) && seriesMatchesKnown
  const catalogImage =
    matchedExactly && nameMatch && !nameMatch.in_library && seriesMatchesKnown
      ? nameMatch.image || ''
      : ''
  // While the series field is empty, a matched name offers its series as the
  // only suggestion. Typing switches to the normal series list.
  const seriesSuggestionValues =
    !series.trim() && nameMatch?.series ? [nameMatch.series] : seriesSuggestions
  // The lookup panel's card shows only while its own field still spells the
  // found character exactly.
  const panelExact = Boolean(
    mudaeExisting && normalizeSeries(mudaeLookupName) === normalizeSeries(mudaeExisting.name),
  )
  const previewNew = (seriesPreview?.items || []).filter((c) => !c.in_library)
  const previewExisting = (seriesPreview?.items || []).filter((c) => c.in_library)

  useEffect(() => {
    // The library's portrait replaces any file chosen before the name resolved,
    // so a stale selection cannot ride along.
    if (catalogImage) setImageFile(null)
  }, [catalogImage])

  useEffect(() => {
    // The rank follows once the name and series both match, so a matched
    // character arrives fully described without the series being forced in.
    if (!seriesMatchesKnown || !nameMatch || rankTouched) return
    const expected = nameMatch.rank || ''
    if (rank !== expected) setRank(expected)
  }, [seriesMatchesKnown, nameMatch, rank, rankTouched])

  // Choosing a suggestion is a deliberate pick, and the suggestion showed the
  // series, so fill it. Typing a name without choosing does not.
  const handlePickName = (item) => {
    if (item?.series) setSeries(item.series)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
    if (duplicateName) {
      const message = `Character "${nameMatch.name}" already exists.`
      setStatus({ type: 'error', message })
      addToast(message, 'error')
      return
    }
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
      // The matched library portrait is authoritative; a file is only for
      // characters the library does not know.
      if (catalogImage) formData.append('image_url', catalogImage)
      else if (imageFile) formData.append('image', imageFile)
      await apiClient.addCharacter(formData)
      await loadCharacters()
      addToast(`Added "${name}"`, 'success')
      setName('')
      setSeries('')
      setRank('')
      setImageFile(null)
      setRankTouched(false)
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
    setMudaeError(null)
    setMudaeExisting(null)
    setStatus(null)
    try {
      // Library first: a name the catalog already knows costs no Mudae request.
      const local = await apiClient.findCatalogCharacter(q)
      if (local.found) {
        if (local.character.in_library) {
          setMudaeExisting(local.character)
          addToast(`Character "${local.character.name}" already exists`, 'error')
          return
        }
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
    setMudaeError(null)
    setMudaeExisting(null)
    setStatus(null)
    try {
      // Catalog first: adding a known character needs no Discord and no ImgChest.
      const local = await apiClient.findCatalogCharacter(q)
      if (local.found) {
        if (local.character.in_library) {
          setMudaeExisting(local.character)
          addToast(`Character "${local.character.name}" already exists.`, 'error')
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
    // One $imartsmi- call for the whole series. $ima is never sent.
    await fetchSeriesPreview(s)
  }

  const fetchSeriesPreview = async (seriesName) => {
    const s = (seriesName || seriesBulkName).trim()
    if (!s) return
    setSeriesBusy(true)
    setSeriesPreview(null)
    setSeriesApplyResult(null)
    addToast(`Fetching "${s}" from Mudae — this can take a moment…`, 'info')
    try {
      const res = await apiClient.mudaeSeriesExtract(s)
      setSeriesPreview(res)
      const found = res.items?.length || 0
      addToast(
        `Found ${found} character${found === 1 ? '' : 's'} in "${res.series || s}"`,
        'success',
      )
    } catch (err) {
      addToast(err.message, 'error')
      setSeriesApplyResult({ error: err.message })
    } finally {
      setSeriesBusy(false)
    }
  }

  const handleApplySeries = async () => {
    if (!seriesPreview) return
    setSeriesApplying(true)
    setSeriesApplyResult(null)
    try {
      const res = await apiClient.mudaeSeriesExtractApply(seriesPreview.series, seriesPreview.items)
      setSeriesApplyResult(res)
      setSeriesPreview(null)
      await loadCharacters()
      addToast(res.message || 'Series applied', 'success')
    } catch (err) {
      addToast(err.message, 'error')
      setSeriesApplyResult({ error: err.message })
    } finally {
      setSeriesApplying(false)
    }
  }

  const lookupPanel = (
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

      {panelExact && <ExistingCharacterCard character={mudaeExisting} />}

      {mudaeError && (
        <p className="form-error" role="alert">
          {mudaeError}
        </p>
      )}

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
                  disabled={seriesBusy}
                />
                <Button
                  variant="primary"
                  type="submit"
                  disabled={seriesBusy || !seriesBulkName.trim()}
                >
                  {seriesBusy ? 'Fetching…' : 'Fetch series'}
                </Button>
              </div>
              <p className="mudae-preview__hint">
                Runs <code>$imartsmi-</code> once for the whole series. You review what will be
                added and updated before anything is saved.
              </p>
            </div>
          </form>

          {seriesBusy && (
            <div className="mudae-progress">
              <div className="mudae-progress__label">
                Fetching the series from Mudae — this can take a moment…
              </div>
            </div>
          )}

          {seriesPreview && !seriesBusy && (
            <div className="mudae-extract">
              <div className="mudae-result">
                <div>
                  <strong>{seriesPreview.series}</strong>
                  {seriesPreview.total ? ` — ${seriesPreview.total} characters` : ''} (
                  {seriesPreview.new_count} new, {seriesPreview.update_count} to update,{' '}
                  {seriesPreview.unchanged_count} unchanged)
                </div>
              </div>

              {previewNew.length > 0 && (
                <details open>
                  <summary>Not in the library ({previewNew.length})</summary>
                  <ul className="mudae-extract__list">
                    {previewNew.map((c) => (
                      <li key={c.name} className="mudae-extract__item">
                        {c.image_url ? (
                          <img
                            src={mudaePreviewSrc(c.image_url)}
                            alt=""
                            className="mudae-extract__img"
                            loading="lazy"
                          />
                        ) : (
                          <span
                            className="mudae-extract__img mudae-extract__img--empty"
                            aria-hidden="true"
                          />
                        )}
                        <span className="mudae-extract__name">{c.name}</span>
                        {c.rank && <span className="mudae-extract__rank">#{c.rank}</span>}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {previewExisting.length > 0 && (
                <details open>
                  <summary>Already in the library ({previewExisting.length})</summary>
                  <ul className="mudae-extract__list">
                    {previewExisting.map((c) => (
                      <li key={c.name} className="mudae-extract__item">
                        {c.image_url ? (
                          <img
                            src={mudaePreviewSrc(c.image_url)}
                            alt=""
                            className="mudae-extract__img"
                            loading="lazy"
                          />
                        ) : (
                          <span
                            className="mudae-extract__img mudae-extract__img--empty"
                            aria-hidden="true"
                          />
                        )}
                        <span className="mudae-extract__name">{c.name}</span>
                        {c.rank && <span className="mudae-extract__rank">#{c.rank}</span>}
                        <span className="mudae-extract__changes">
                          {c.changes.length ? `updates ${c.changes.join(', ')}` : 'no change'}
                        </span>
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              <div className="mudae-row mudae-extract__actions">
                <Button variant="primary" disabled={seriesApplying} onClick={handleApplySeries}>
                  {seriesApplying
                    ? 'Saving…'
                    : `Apply — add ${seriesPreview.new_count}, update ${seriesPreview.update_count}`}
                </Button>
                <Button
                  variant="secondary"
                  disabled={seriesApplying}
                  onClick={() => setSeriesPreview(null)}
                >
                  Discard
                </Button>
              </div>
            </div>
          )}

          {seriesApplyResult && !seriesApplying && (
            <div className="mudae-result">
              {seriesApplyResult.error ? (
                <div className="form-error">{seriesApplyResult.error}</div>
              ) : (
                <>
                  <div>{seriesApplyResult.message}</div>
                  {Array.isArray(seriesApplyResult.rejected) &&
                    seriesApplyResult.rejected.length > 0 && (
                      <details>
                        <summary>Rejected ({seriesApplyResult.rejected.length})</summary>
                        <ul className="mudae-scroll-list">
                          {seriesApplyResult.rejected.map((f) => (
                            <li key={f.name} className="mudae-item--warn">
                              {f.name}: {f.error}
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                </>
              )}
            </div>
          )}
        </>
      )}
      {!mudaeConfigured && (
        <p className="mudae-setup-hint">
          Bulk series import needs Mudae, which is not configured. Lookup and add still work from
          the library.
        </p>
      )}
    </div>
  )

  const manualPanel = (
    <div className="edit-form-container add-char-panel">
      <h3 className="section-heading">Manual add</h3>
      <form onSubmit={handleSubmit} className="add-char-form field-stack">
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
        {duplicateName && <ExistingCharacterCard character={nameMatch} />}
        <Field label="Series" htmlFor="addCharSeries" className="full-width">
          <SeriesSuggestInput
            id="addCharSeries"
            className="ui-input"
            placeholder="Series Name"
            value={series}
            onChange={(e) => setSeries(e.target.value)}
            suggestions={seriesSuggestionValues}
            ariaLabel="Series suggestions"
            ariaInvalid={seriesMismatch}
          />
          {seriesMismatch && (
            <p className="form-error" role="alert">
              Series doesn&apos;t match — &quot;{nameMatch.name}&quot; is in &quot;
              {nameMatch.series}&quot;.
            </p>
          )}
        </Field>
        <Field label="Rank (Optional)" htmlFor="addCharRank" className="full-width">
          <Input
            id="addCharRank"
            type="number"
            placeholder="Leave blank to skip"
            value={rank}
            onChange={(e) => {
              setRank(e.target.value)
              setRankTouched(true)
            }}
          />
        </Field>
        <Field label="Main Photo (Optional)" htmlFor="addCharImage" className="full-width">
          {catalogImage ? (
            <div className="add-char-image-preview">
              <img src={catalogImage} alt="" className="add-char-image-preview__img" />
              <p className="mudae-preview__hint">
                The library&apos;s main image is used automatically and cannot be replaced.
              </p>
            </div>
          ) : (
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
          )}
        </Field>
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
  )

  return (
    <Card as="section" padding="lg" className="add-layout--workbench add-type add-type--ramp">
      <h1 className="page-title">Add New Character</h1>
      <div className="add-layout__columns">
        {lookupPanel}
        {manualPanel}
      </div>
    </Card>
  )
}

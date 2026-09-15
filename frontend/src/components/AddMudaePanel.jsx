import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import { useCatalogSuggest } from '../hooks/useCatalogSuggest'
import { useStore } from '../store/useStore'
import { normalizeSeries } from '../utils/normalizeSeries'
import ExistingCharacterCard from './ExistingCharacterCard'
import { GenderMarks } from './GenderMarks'
import SeriesSuggestInput from './SeriesSuggestInput'
import { Button } from './ui'

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

function mudaeCandidatesFromResponse(res) {
  if (Array.isArray(res?.candidate_matches) && res.candidate_matches.length) {
    return res.candidate_matches.map((m) => ({
      name: m.name,
      label: m.label || (m.series ? `${m.name} - ${m.series}` : m.name),
    }))
  }
  return (res?.candidates || []).map((n) => ({ name: n, label: n }))
}

/**
 * The left-hand panel of the Add workbench: look a character up by name and
 * save it, or bulk-add a whole series from one `$imartsmi-`.
 *
 * It owns every bit of Mudae state, because none of it is the manual form's
 * business — a lookup only hands the found record back through `onPrefill`, so
 * the form beside it fills in without either panel reaching into the other.
 */
export default function AddMudaePanel({ name, onPrefill, onError, onClearError }) {
  const navigate = useNavigate()
  const addToast = useStore((s) => s.addToast)

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
  // A message shown inside the lookup panel, e.g. "already exists".
  const [mudaeError, setMudaeError] = useState(null)
  // The character a lookup found already in the library, shown as a clickable card.
  const [mudaeExisting, setMudaeExisting] = useState(null)

  useEffect(() => {
    apiClient
      .mudaeStatus()
      .then((r) => setMudaeConfigured(!!r.configured))
      .catch(() => setMudaeConfigured(false))
  }, [])

  const panelNameSuggestions = useCatalogSuggest(mudaeLookupName, { kind: 'characters', limit: 8 })
  const bulkSeriesSuggestions = useCatalogSuggest(seriesBulkName, { kind: 'series', limit: 20 })

  const panelNameItems = useMemo(
    () =>
      panelNameSuggestions.map((c) => ({
        value: c.name,
        label: c.name,
        meta: c.series || undefined,
      })),
    [panelNameSuggestions],
  )

  // The lookup panel's card shows only while its own field still spells the
  // found character exactly.
  const panelExact = Boolean(
    mudaeExisting && normalizeSeries(mudaeLookupName) === normalizeSeries(mudaeExisting.name),
  )
  const previewNew = (seriesPreview?.items || []).filter((c) => !c.in_library)
  const previewExisting = (seriesPreview?.items || []).filter((c) => c.in_library)

  const applyMudaeCharacter = (character) => {
    if (!character) return
    onPrefill(character)
    // Catalog results carry `image`; Mudae results carry `image_url`. Normalise
    // so the preview and the panel render either.
    setMudaePreview({
      ...character,
      image_url: character.image_url || character.image || '',
    })
    setMudaeCandidates([])
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
    onClearError?.()
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
      onError(err.message)
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
    onClearError?.()
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
      addToast(res.message || `Added "${addedName}"`, 'success')
      setMudaePreview(null)
      setMudaeCandidates([])
      setMudaeLookupName('')
      setTimeout(() => navigate(`/character/${encodeURIComponent(addedName)}`), 500)
    } catch (err) {
      addToast(err.message, 'error')
      onError(err.message)
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
      addToast(res.message || 'Series applied', 'success')
    } catch (err) {
      addToast(err.message, 'error')
      setSeriesApplyResult({ error: err.message })
    } finally {
      setSeriesApplying(false)
    }
  }

  return (
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
            <div className="mudae-preview__meta">
              {mudaePreview.series || '—'}
              <GenderMarks isFemale={mudaePreview.is_female} isMale={mudaePreview.is_male} />
            </div>
            {mudaePreview.pools && <div className="mudae-preview__meta">{mudaePreview.pools}</div>}
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
}

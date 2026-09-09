import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import SeriesSuggestInput from '../components/SeriesSuggestInput'
import { Button, Card } from '../components/ui'
import { useStore } from '../store/useStore'

/** Discord/CDN images often fail as bare <img src>; preview via backend proxy. */
function mudaePreviewSrc(imageUrl) {
  if (!imageUrl) return ''
  if (
    imageUrl.startsWith('http://') ||
    imageUrl.startsWith('https://') ||
    imageUrl.startsWith('//')
  ) {
    const absolute = imageUrl.startsWith('//') ? `https:${imageUrl}` : imageUrl
    return `/api/mudae/proxy-image?url=${encodeURIComponent(absolute)}`
  }
  return getImageUrl(imageUrl)
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

  const navigate = useNavigate()
  const characters = useStore((s) => s.characters)
  const savedCharacters = useStore((s) => s.savedCharacters)
  const loadCharacters = useStore((s) => s.loadCharacters)
  const addToast = useStore((s) => s.addToast)

  useEffect(() => {
    apiClient
      .mudaeStatus()
      .then((r) => setMudaeConfigured(!!r.configured))
      .catch(() => setMudaeConfigured(false))
  }, [])

  const seriesSuggestions = useMemo(() => {
    const seen = new Set()
    for (const c of [...characters, ...savedCharacters]) {
      const s = (c.series || '').trim()
      if (s) seen.add(s)
    }
    return [...seen].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: 'base' }))
  }, [characters, savedCharacters])

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!name.trim()) return
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
    setMudaePreview(character)
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

      {mudaeConfigured === false && (
        <p className="mudae-setup-hint">Mudae import is not available.</p>
      )}

      {mudaeConfigured && (
        <div className="edit-form-container mudae-panel">
          <h3 className="section-heading">From Mudae</h3>
          <p className="mudae-note">
            Looks up claim rank, series, and main image using Mudae <code>$im</code> and{' '}
            <code>$ima</code>.
          </p>

          <div className="edit-group full-width">
            <label htmlFor="mudaeCharName">Character name</label>
            <div className="mudae-row">
              <input
                id="mudaeCharName"
                type="text"
                className="modern-input"
                placeholder="e.g. Rem"
                value={mudaeLookupName}
                onChange={(e) => setMudaeLookupName(e.target.value)}
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
                {mudaeBusy ? 'Working…' : 'Add from Mudae'}
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
                  The manual form below was pre-filled, or use &quot;Add from Mudae&quot; to upload
                  the image and save.
                </p>
              </div>
            </div>
          )}

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
                  suggestions={seriesSuggestions}
                  disabled={seriesBusy || seriesResolving}
                />
                <Button
                  variant="primary"
                  type="submit"
                  disabled={seriesBusy || seriesResolving || !seriesBulkName.trim()}
                >
                  {seriesResolving ? 'Checking…' : seriesBusy ? 'Importing…' : 'Add entire series'}
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
                  <summary>Skipped — already in library ({seriesProgress.skipped.length})</summary>
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
        </div>
      )}

      <div className="edit-form-container add-char-panel">
        <h3 className="section-heading">Manual add</h3>
        <form onSubmit={handleSubmit} className="add-char-form">
          <div className="edit-group full-width">
            <label htmlFor="addCharName">Character Name</label>
            <input
              id="addCharName"
              type="text"
              className="modern-input"
              placeholder="e.g. Saber"
              value={name}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </div>
          <div className="edit-group full-width">
            <label htmlFor="addCharSeries">Series</label>
            <SeriesSuggestInput
              id="addCharSeries"
              placeholder="Series Name"
              value={series}
              onChange={(e) => setSeries(e.target.value)}
              suggestions={seriesSuggestions}
            />
          </div>
          <div className="edit-group full-width">
            <label htmlFor="addCharRank">Rank (Optional)</label>
            <input
              id="addCharRank"
              type="number"
              className="modern-input"
              placeholder="Leave blank to skip"
              value={rank}
              onChange={(e) => setRank(e.target.value)}
            />
          </div>
          <div className="edit-group full-width">
            <label>Main Photo (Optional)</label>
            <div
              className="file-upload-box"
              onClick={() => document.getElementById('addCharImage')?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) =>
                e.key === 'Enter' && document.getElementById('addCharImage')?.click()
              }
            >
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
                style={{ display: 'none' }}
                onChange={(e) => setImageFile(e.target.files?.[0] || null)}
              />
            </div>
          </div>
          <div className="edit-actions add-char-actions">
            <Button variant="primary" type="submit" disabled={loading}>
              {loading ? 'Adding...' : 'Add Character'}
            </Button>
          </div>
          {status?.type === 'error' && (
            <div id="addCharStatus" className="form-error">
              {status.message}
            </div>
          )}
        </form>
      </div>
    </Card>
  )
}

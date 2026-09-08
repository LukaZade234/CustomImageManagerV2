import { useState, useMemo, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import { useStore } from '../store/useStore'
import SeriesSuggestInput from '../components/SeriesSuggestInput'

/** Discord/CDN images often fail as bare <img src>; preview via backend proxy. */
function mudaePreviewSrc(imageUrl) {
  if (!imageUrl) return ''
  if (imageUrl.startsWith('http://') || imageUrl.startsWith('https://') || imageUrl.startsWith('//')) {
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
    apiClient.mudaeStatus()
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
    <div id="addPage" className="add-page">
      <h2 className="page-title">Add New Character</h2>

      {mudaeConfigured === false && (
        <p className="mudae-setup-hint" style={{ maxWidth: '640px', marginBottom: '1.25rem', opacity: 0.85 }}>
          Mudae import is not available.
        </p>
      )}

      {mudaeConfigured && (
        <div className="edit-form-container mudae-panel" style={{ maxWidth: '640px', margin: '0 0 2rem' }}>
          <h3 className="section-heading" style={{ marginTop: 0 }}>From Mudae</h3>
          <p style={{ marginTop: 0, opacity: 0.85, fontSize: '0.95em' }}>
            Looks up claim rank, series, and main image using Mudae <code>$im</code> and <code>$ima</code>.
          </p>

          <div className="edit-group full-width">
            <label htmlFor="mudaeCharName">Character name</label>
            <div className="mudae-row" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <input
                id="mudaeCharName"
                type="text"
                className="modern-input"
                style={{ flex: '1 1 200px' }}
                placeholder="e.g. Rem"
                value={mudaeLookupName}
                onChange={(e) => setMudaeLookupName(e.target.value)}
                disabled={mudaeBusy}
              />
              <button
                type="button"
                className="action-btn secondary"
                disabled={mudaeBusy || !mudaeLookupName.trim()}
                onClick={() => handleMudaeLookup()}
              >
                {mudaeBusy ? 'Querying…' : 'Lookup'}
              </button>
              <button
                type="button"
                className="action-btn primary"
                disabled={mudaeBusy || !(mudaePreview?.name || mudaeLookupName.trim())}
                onClick={handleMudaeAdd}
              >
                {mudaeBusy ? 'Working…' : 'Add from Mudae'}
              </button>
            </div>
          </div>

          {mudaeCandidates.length > 0 && (
            <div className="mudae-candidates" style={{ marginTop: '0.75rem' }}>
              <div style={{ marginBottom: '0.35rem', fontWeight: 600 }}>Pick a match:</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                {mudaeCandidates.map((c) => (
                  <button
                    key={`${c.name}-${c.label}`}
                    type="button"
                    className="action-btn secondary"
                    disabled={mudaeBusy}
                    onClick={() => {
                      setMudaeLookupName(c.name)
                      handleMudaeLookup(c.name)
                    }}
                  >
                    {c.label}
                  </button>
                ))}
              </div>
            </div>
          )}

          {mudaePreview && (
            <div className="mudae-preview" style={{ display: 'flex', gap: '1rem', marginTop: '1rem', alignItems: 'flex-start' }}>
              {mudaePreview.image_url && (
                <img
                  src={mudaePreviewSrc(mudaePreview.image_url)}
                  alt={mudaePreview.name}
                  style={{ width: 96, height: 128, objectFit: 'cover', borderRadius: 4, background: '#eee' }}
                />
              )}
              <div>
                <div><strong>{mudaePreview.name}</strong></div>
                <div style={{ opacity: 0.85 }}>{mudaePreview.series || '—'}</div>
                <div style={{ opacity: 0.85 }}>Claim rank: {mudaePreview.rank ? `#${mudaePreview.rank}` : '—'}</div>
                <p style={{ fontSize: '0.85em', opacity: 0.75, marginBottom: 0 }}>
                  The manual form below was pre-filled, or use &quot;Add from Mudae&quot; to upload the image and save.
                </p>
              </div>
            </div>
          )}

          <hr style={{ margin: '1.5rem 0', opacity: 0.25 }} />

          <form onSubmit={handleSeriesBulk}>
            <div className="edit-group full-width">
              <label htmlFor="mudaeSeriesBulk">Bulk-add series</label>
              <div className="mudae-row" style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <SeriesSuggestInput
                  id="mudaeSeriesBulk"
                  placeholder="Exact series name"
                  value={seriesBulkName}
                  onChange={(e) => setSeriesBulkName(e.target.value)}
                  suggestions={seriesSuggestions}
                  disabled={seriesBusy || seriesResolving}
                />
                <button type="submit" className="action-btn primary" disabled={seriesBusy || seriesResolving || !seriesBulkName.trim()}>
                  {seriesResolving ? 'Checking…' : seriesBusy ? 'Importing…' : 'Add entire series'}
                </button>
                {seriesBusy && (
                  <button
                    type="button"
                    className="action-btn secondary"
                    disabled={seriesCancelling}
                    onClick={handleCancelSeries}
                  >
                    {seriesCancelling ? 'Cancelling…' : 'Cancel import'}
                  </button>
                )}
              </div>
              <p style={{ fontSize: '0.85em', opacity: 0.75, marginTop: '0.4rem' }}>
                Runs <code>$ima</code> then <code>$im</code> per character. Large series can take several minutes; existing names are skipped.
              </p>
              {seriesCandidates.length > 0 && (
                <div className="mudae-candidates" style={{ marginTop: '0.75rem' }}>
                  <div style={{ marginBottom: '0.35rem', fontWeight: 600 }}>Pick a series:</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.4rem' }}>
                    {seriesCandidates.map((c) => (
                      <button
                        key={`${c.name}-${c.label}`}
                        type="button"
                        className="action-btn secondary"
                        disabled={seriesBusy || seriesResolving}
                        onClick={() => handlePickSeriesCandidate(c.name)}
                      >
                        {c.label}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </form>

          {seriesProgress && seriesBusy && (
            <div className="mudae-series-progress" style={{ marginTop: '1rem', fontSize: '0.9em' }}>
              <div style={{ marginBottom: '0.5rem' }}>
                {seriesProgress.phase === 'starting' && 'Querying Mudae for series list…'}
                {seriesProgress.phase === 'delay' && (
                  <>Found {seriesProgress.totalListed} character{seriesProgress.totalListed !== 1 ? 's' : ''} in &quot;{seriesProgress.series}&quot; — waiting before lookups…</>
                )}
                {seriesProgress.phase === 'adding' && seriesProgress.current && (
                  <>
                    Adding: <strong>{seriesProgress.current}</strong>
                    {' '}
                    ({seriesProgress.added.length + seriesProgress.skipped.length + seriesProgress.failed.length}
                    {seriesProgress.totalListed ? ` / ${seriesProgress.totalListed}` : ''})
                  </>
                )}
                {seriesProgress.phase === 'retry' && 'Retrying failed characters…'}
                {seriesProgress.phase === 'cancelled' && 'Stopping import…'}
              </div>
              {seriesProgress.added.length > 0 && (
                <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.2rem', maxHeight: '160px', overflowY: 'auto' }}>
                  {seriesProgress.added.map((c) => (
                    <li key={c.name} style={{ color: '#198754' }}>{c.name}</li>
                  ))}
                </ul>
              )}
              {seriesProgress.skipped.length > 0 && (
                <details open style={{ marginTop: '0.5rem' }}>
                  <summary style={{ cursor: 'pointer' }}>
                    Skipped — already in library ({seriesProgress.skipped.length})
                  </summary>
                  <ul style={{ margin: '0.35rem 0 0', paddingLeft: '1.2rem', maxHeight: '160px', overflowY: 'auto' }}>
                    {seriesProgress.skipped.map((name) => (
                      <li key={name} style={{ color: '#856404' }}>{name}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}

          {seriesResult && !seriesResult.error && !seriesBusy && (
            <div style={{ marginTop: '0.75rem', fontSize: '0.9em' }}>
              <div>{seriesResult.message}</div>
              {Array.isArray(seriesResult.added) && seriesResult.added.length > 0 && (
                <details open={seriesResult.cancelled} style={{ marginTop: '0.4rem' }}>
                  <summary>Added ({seriesResult.added.length})</summary>
                  <ul>
                    {seriesResult.added.map((c) => (
                      <li key={c.name}>{c.name}</li>
                    ))}
                  </ul>
                </details>
              )}
              {Array.isArray(seriesResult.skipped) && seriesResult.skipped.length > 0 && (
                <details style={{ marginTop: '0.4rem' }}>
                  <summary>Skipped — already in library ({seriesResult.skipped.length})</summary>
                  <ul>
                    {seriesResult.skipped.map((name) => (
                      <li key={name}>{name}</li>
                    ))}
                  </ul>
                </details>
              )}
              {Array.isArray(seriesResult.failed) && seriesResult.failed.length > 0 && (
                <details style={{ marginTop: '0.4rem' }}>
                  <summary>Failed ({seriesResult.failed.length})</summary>
                  <ul>
                    {seriesResult.failed.map((f) => (
                      <li key={f.name}>{f.name}: {f.error}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
          {seriesResult?.error && (
            <div style={{ marginTop: '0.75rem', color: '#dc3545' }}>{seriesResult.error}</div>
          )}
        </div>
      )}

      <div className="edit-form-container" style={{ maxWidth: '500px', margin: 0 }}>
        <h3 className="section-heading" style={{ marginTop: 0 }}>Manual add</h3>
        <form onSubmit={handleSubmit} className="add-char-form" style={{ maxWidth: '100%' }}>
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
          <div className="edit-group full-width" style={{ marginTop: '10px' }}>
            <label>Main Photo (Optional)</label>
            <div
              className="file-upload-box"
              onClick={() => document.getElementById('addCharImage')?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && document.getElementById('addCharImage')?.click()}
            >
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#6c757d" strokeWidth="2" style={{ marginBottom: '8px', display: 'block' }}>
                <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                <circle cx="8.5" cy="8.5" r="1.5" />
                <polyline points="21 15 16 10 5 21" />
              </svg>
              <span id="addCharImageLabel" style={{ color: '#6c757d', fontSize: '0.9em' }}>
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
          <div className="edit-actions" style={{ justifyContent: 'flex-start', marginTop: '25px' }}>
            <button type="submit" disabled={loading} className="action-btn primary">
              {loading ? 'Adding...' : 'Add Character'}
            </button>
          </div>
          {status?.type === 'error' && (
            <div id="addCharStatus" style={{ marginTop: '15px', color: '#dc3545' }}>{status.message}</div>
          )}
        </form>
      </div>
    </div>
  )
}

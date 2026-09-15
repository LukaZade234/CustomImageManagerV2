import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { apiClient, getPortraitUrl } from '../api'
import AddManualForm from '../components/AddManualForm'
import AddMudaePanel from '../components/AddMudaePanel'
import { Card } from '../components/ui'
import { useCatalogMatch, useCatalogSuggest } from '../hooks/useCatalogSuggest'
import { useMe } from '../queries/me'
import { useStore } from '../store/useStore'
import { normalizeSeries } from '../utils/normalizeSeries'

/**
 * The Add workbench: the Mudae lookup panel and the manual form side by side.
 *
 * This page owns the one thing both panels share — the record being typed — so a
 * lookup in one can pre-fill the other. Everything Mudae-specific lives in
 * `AddMudaePanel` and everything form-specific in `AddManualForm`; this file is
 * the catalog-match logic that decides what the form offers and what it refuses.
 */
export default function AddPage() {
  const [name, setName] = useState('')
  const [series, setSeries] = useState('')
  const [rank, setRank] = useState('')
  const [imageFile, setImageFile] = useState(null)
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(false)
  // Gender and roulette pools, used to narrow the name suggestions. Optional:
  // adding a character never requires them, exactly like Rank and Main Photo.
  const [poolFilter, setPoolFilter] = useState([])
  // The character whose pools were last auto-selected, so a match does not
  // clobber the visitor's own toggles on every render.
  const autoPoolName = useRef(null)
  // The library fills the rank once the series is chosen, until the field is edited.
  const [rankTouched, setRankTouched] = useState(false)

  const navigate = useNavigate()
  const addToast = useStore((s) => s.addToast)
  const { data: me } = useMe()
  // A search result that is in the catalog but not the library links here with
  // the name in the query string, so the form opens ready to add it. The rest of
  // the record (series, rank, portrait, pools) is filled from the catalog rather
  // than left for the visitor to retype; the portrait follows from the match
  // once the series agrees.
  const [searchParams] = useSearchParams()
  const prefillName = searchParams.get('name') || ''
  useEffect(() => {
    if (!prefillName) return undefined
    setName(prefillName)
    let cancelled = false
    apiClient
      .findCatalogCharacter(prefillName)
      .then((res) => {
        if (cancelled || !res?.found || !res.character) return
        const c = res.character
        if (c.series) setSeries(c.series)
        if (c.rank) setRank(c.rank)
        if (c.facets?.length) {
          setPoolFilter(c.facets)
          autoPoolName.current = c.name || prefillName
        }
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [prefillName])

  // Catalog-backed suggestions and the library's own record for the typed name.
  // The name combobox gets the typed series as a hint, so a named series offers
  // its characters until the visitor starts typing a name of their own.
  const nameSuggestions = useCatalogSuggest(name, {
    kind: 'characters',
    limit: 8,
    series,
    pools: poolFilter,
  })
  const seriesSuggestions = useCatalogSuggest(series, { kind: 'series', limit: 20 })
  const nameMatch = useCatalogMatch(name)

  const togglePool = (key) =>
    setPoolFilter((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : [...cur, key]))

  const nameSuggestionItems = useMemo(
    () =>
      nameSuggestions.map((c) => ({
        value: c.name,
        label: c.name,
        meta: c.series || undefined,
        series: c.series || '',
        facets: c.facets || [],
      })),
    [nameSuggestions],
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
  // The preview shows the mirrored portrait when the catalog has one; the form
  // still submits the canonical URL, so the working row keeps pointing at the
  // catalog's own portrait rather than a copy of it.
  const catalogImageSrc = catalogImage ? getPortraitUrl(catalogImage, nameMatch?.image_thumb) : ''
  // While the series field is empty, a matched name offers its series as the
  // only suggestion. Typing switches to the normal series list.
  const seriesSuggestionValues =
    !series.trim() && nameMatch?.series ? [nameMatch.series] : seriesSuggestions

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

  useEffect(() => {
    // A matched character selects its own gender and roulette pools. It is only
    // a suggestion -- the visitor can clear it -- so this never blocks adding.
    if (!matchedExactly || !nameMatch || autoPoolName.current === nameMatch.name) return
    autoPoolName.current = nameMatch.name
    setPoolFilter(nameMatch.facets || [])
  }, [matchedExactly, nameMatch])

  // Choosing a suggestion is a deliberate pick, and the suggestion showed the
  // series, so fill it. Typing a name without choosing does not.
  const handlePickName = (item) => {
    if (item?.series) setSeries(item.series)
    if (item?.facets?.length) {
      setPoolFilter(item.facets)
      autoPoolName.current = item.value
    }
  }

  // A Mudae lookup hands back the record it found, and this fills the manual
  // form with it. The catalog portrait is authoritative, so any file chosen
  // before the lookup is dropped.
  const handlePrefill = (character) => {
    setName(character.name || '')
    setSeries(character.series || '')
    setRank(character.rank || '')
    setImageFile(null)
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

  const form = {
    name,
    series,
    rank,
    imageFile,
    status,
    loading,
    poolFilter,
    nameSuggestionItems,
    seriesSuggestionValues,
    duplicateName,
    seriesMismatch,
    nameMatch,
    catalogImage,
    catalogImageSrc,
    canAddImages: Boolean(me?.signed_in),
    // A brand-new character needs an account; a name the catalog already knows
    // is "from the library" and may be added from a cookie alone.
    canAddNewCharacter: Boolean(me?.signed_in) || Boolean(matchedExactly && nameMatch),
    onNameChange: setName,
    onSeriesChange: setSeries,
    onRankChange: (value) => {
      setRank(value)
      setRankTouched(true)
    },
    onImageChange: setImageFile,
    onPickName: handlePickName,
    onTogglePool: togglePool,
    onSubmit: handleSubmit,
  }

  return (
    <Card as="section" padding="lg" className="add-layout--workbench add-type add-type--ramp">
      <h1 className="page-title">Add New Character</h1>
      <div className="add-layout__columns">
        <AddMudaePanel
          name={name}
          onPrefill={handlePrefill}
          onError={(message) => setStatus({ type: 'error', message })}
          onClearError={() => setStatus(null)}
        />
        <AddManualForm form={form} />
      </div>
    </Card>
  )
}

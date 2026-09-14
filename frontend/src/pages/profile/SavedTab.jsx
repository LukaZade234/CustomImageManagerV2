import { useMemo, useState } from 'react'
import { getPortraitUrl } from '../../api'
import { MODE_OPTIONS } from '../../components/FilterBar'
import { useRemoveSaved, useSavedCharacters } from '../../queries/saved'
import { useStore } from '../../store/useStore'
import CardGrid from './CardGrid'
import ListTab from './ListTab'
import { byAsc, byText, useFilteredList } from './useFilteredList'

/**
 * Bookmarked characters. This was `/saved`, its own top-level page; it moved
 * here so that everything belonging to you is in one place.
 */

const SORTS = {
  alphabet: { label: 'Alphabet', compare: byText('name'), order: 'asc' },
  recent: { label: 'Most recent', compare: byAsc('updated_at'), order: 'desc' },
}
const FIELDS = { name: ['name'], series: ['series'] }

export default function SavedTab() {
  const { data: savedCharacters = [] } = useSavedCharacters()
  const removeSaved = useRemoveSaved()
  const addToast = useStore((s) => s.addToast)
  const mode = useStore((s) => s.searchMode)
  const setMode = useStore((s) => s.setSearchMode)
  const [busy, setBusy] = useState(null)

  // The server joins the library row into /api/saved, so the series, portrait
  // and recency arrive with the bookmark rather than from a downloaded roster.
  const rows = savedCharacters.map((saved) => ({
    name: saved.name,
    series: saved.series ?? '',
    image: saved.image ?? '',
    image_thumb: saved.image_thumb ?? '',
    updated_at: saved.updated_at ?? '',
  }))

  const fields = useMemo(() => FIELDS[mode] ?? FIELDS.name, [mode])
  const filter = useFilteredList(rows, fields, SORTS)

  const unsave = async (name) => {
    setBusy(name)
    try {
      await removeSaved.mutateAsync(name)
      addToast('Removed from saved', 'success')
    } catch (err) {
      addToast(err.message, 'error')
    } finally {
      setBusy(null)
    }
  }

  return (
    <ListTab
      title="Saved characters"
      blurb="Bookmarks, kept to this browser unless you sign in."
      searchLabel="Search saved"
      filter={filter}
      total={rows.length}
      mode={mode}
      onMode={setMode}
      modeOptions={MODE_OPTIONS}
      emptyTitle="No saved characters yet"
      emptyBody="Bookmark a character from its page and it will show up here for quick access."
    >
      {(items) => (
        <CardGrid
          uniform
          items={items.map((char) => ({
            key: char.name,
            href: `/character/${encodeURIComponent(char.name)}`,
            image: char.image ? getPortraitUrl(char.image, char.image_thumb) : '',
            title: char.name,
            subtitle: char.series,
            action: 'Unsave',
            busy: busy === char.name,
            onAction: () => unsave(char.name),
          }))}
        />
      )}
    </ListTab>
  )
}

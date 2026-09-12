import { useState } from 'react'
import { getImageUrl } from '../../api'
import { useStore } from '../../store/useStore'
import CardGrid from './CardGrid'
import ListTab from './ListTab'
import { byText, useFilteredList } from './useFilteredList'

/**
 * Bookmarked characters. This was `/saved`, its own top-level page; it moved
 * here so that everything belonging to you is in one place.
 */

const SORTS = {
  name: { label: 'Name (A–Z)', compare: byText('name') },
  series: { label: 'Series (A–Z)', compare: byText('series') },
}
const FIELDS = ['name', 'series']

export default function SavedTab() {
  const savedCharacters = useStore((s) => s.savedCharacters)
  const characters = useStore((s) => s.characters)
  const removeSaved = useStore((s) => s.removeSaved)
  const addToast = useStore((s) => s.addToast)
  const [busy, setBusy] = useState(null)

  // The saved list holds names; the series and portrait come from the library.
  const rows = savedCharacters.map((saved) => {
    const full = characters.find((c) => c.name === saved.name)
    return { name: saved.name, series: full?.series ?? '', image: full?.image ?? '' }
  })

  const filter = useFilteredList(rows, FIELDS, SORTS)

  const unsave = async (name) => {
    setBusy(name)
    try {
      await removeSaved(name)
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
      emptyTitle="No saved characters yet"
      emptyBody="Bookmark a character from its page and it will show up here for quick access."
    >
      {(items) => (
        <CardGrid
          uniform
          items={items.map((char) => ({
            key: char.name,
            href: `/character/${encodeURIComponent(char.name)}`,
            image: char.image ? getImageUrl(char.image) : '',
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

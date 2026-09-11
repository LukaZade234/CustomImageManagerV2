import { useCallback, useEffect, useState } from 'react'
import { apiClient, getImageUrl } from '../../api'
import { apiUrl } from '../../config'
import { useStore } from '../../store/useStore'
import CardGrid, { cardRatio } from './CardGrid'
import ListTab from './ListTab'
import { byDesc, byText, useFilteredList } from './useFilteredList'

/**
 * Images you removed, across every character. All of them restorable, because
 * nothing is ever deleted from the image host — a removed image is still live
 * at its URL, which is what makes removal cheap to undo.
 */

const SORTS = {
  recent: { label: 'Recently removed', compare: byDesc('removed_at') },
  character: { label: 'Character (A–Z)', compare: byText('character') },
}
const FIELDS = ['character', 'removed_reason']

export default function RemovedTab() {
  const addToast = useStore((s) => s.addToast)
  const [rows, setRows] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    setRows(await apiClient.getMyRemoved().catch(() => []))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const filter = useFilteredList(rows, FIELDS, SORTS)

  const restore = async (row) => {
    setBusyId(row.id)
    try {
      // Restore is addressed by character and URL, not by image id.
      await apiClient.restoreImages(row.character, [row.url])
      setRows((list) => list.filter((r) => r.id !== row.id))
      addToast(`Restored to ${row.character}`, 'success')
    } catch (e) {
      addToast(e.message || 'Could not restore that image', 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <ListTab
      title="Removed images"
      blurb="Nothing is ever deleted from the image host, so anything here can be put back."
      searchLabel="Search by character"
      filter={filter}
      total={rows?.length ?? 0}
      emptyTitle="Nothing removed"
      emptyBody="Images you remove stay here in case you change your mind."
    >
      {(items) => (
        <CardGrid
          items={items.map((row) => ({
            key: row.id,
            href: `/character/${encodeURIComponent(row.character)}`,
            image: row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url),
            ratio: cardRatio(row.width, row.height),
            title: row.character,
            subtitle: row.removed_reason,
            action: 'Restore',
            busy: busyId === row.id,
            onAction: () => restore(row),
          }))}
        />
      )}
    </ListTab>
  )
}

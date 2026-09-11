import { useCallback, useEffect, useState } from 'react'
import { apiClient, getImageUrl } from '../../api'
import { apiUrl } from '../../config'
import { useStore } from '../../store/useStore'
import CardGrid, { cardRatio } from './CardGrid'
import ListTab from './ListTab'
import { byDesc, byText, useFilteredList } from './useFilteredList'

/**
 * Images you have hidden, across every character.
 *
 * Hiding is otherwise reachable only from the character page holding the image,
 * so anyone who hid something and did not recall where had no way back to it.
 */

const SORTS = {
  recent: { label: 'Recently hidden', compare: byDesc('hidden_at') },
  character: { label: 'Character (A–Z)', compare: byText('character') },
}
const FIELDS = ['character']

export default function HiddenTab() {
  const addToast = useStore((s) => s.addToast)
  const [rows, setRows] = useState(null)
  const [busyId, setBusyId] = useState(null)

  const load = useCallback(async () => {
    setRows(await apiClient.getMyHidden().catch(() => []))
  }, [])

  useEffect(() => {
    load()
  }, [load])

  const filter = useFilteredList(rows, FIELDS, SORTS)

  const unhide = async (row) => {
    setBusyId(row.id)
    try {
      await apiClient.unhideImages([row.id])
      setRows((list) => list.filter((r) => r.id !== row.id))
      addToast('Image is visible to you again', 'success')
    } catch (e) {
      addToast(e.message || 'Could not unhide that image', 'error')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <ListTab
      title="Hidden images"
      blurb="Hidden only for you — nobody else is affected, and the image is not removed."
      searchLabel="Search by character"
      filter={filter}
      total={rows?.length ?? 0}
      emptyTitle="Nothing hidden"
      emptyBody="Images you hide from a character page will collect here."
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
            action: 'Unhide',
            busy: busyId === row.id,
            onAction: () => unhide(row),
          }))}
        />
      )}
    </ListTab>
  )
}

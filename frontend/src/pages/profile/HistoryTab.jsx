import { useEffect, useState } from 'react'
import { apiClient, getImageUrl } from '../../api'
import CardGrid from './CardGrid'
import ListTab from './ListTab'
import { byDesc, byText, useFilteredList } from './useFilteredList'

/**
 * Characters you have looked at, most recent first.
 *
 * Each character appears once however often you visited: the server keeps one
 * row per person per character per hour, so this is "where have I been" rather
 * than a raw log of page loads.
 */

const SORTS = {
  recent: { label: 'Recently viewed', compare: byDesc('last_viewed') },
  visits: { label: 'Most visited', compare: byDesc('visits') },
  name: { label: 'Name (A–Z)', compare: byText('name') },
  images: { label: 'Most images', compare: byDesc('images') },
}
const FIELDS = ['name', 'series']

/** "3 days ago" reads better than a timestamp in a list you scan. */
function relativeDay(iso) {
  if (!iso) return ''
  const then = new Date(iso)
  if (Number.isNaN(then.getTime())) return ''
  const days = Math.floor((Date.now() - then.getTime()) / 86400000)
  if (days <= 0) return 'today'
  if (days === 1) return 'yesterday'
  if (days < 30) return `${days} days ago`
  const months = Math.floor(days / 30)
  return months === 1 ? 'a month ago' : `${months} months ago`
}

export default function HistoryTab() {
  const [rows, setRows] = useState(null)

  useEffect(() => {
    apiClient
      .getMyHistory()
      .then(setRows)
      .catch(() => setRows([]))
  }, [])

  const filter = useFilteredList(rows, FIELDS, SORTS)

  return (
    <ListTab
      title="Recently viewed"
      blurb="Kept to this browser unless you sign in, and only for 90 days."
      searchLabel="Search history"
      filter={filter}
      total={rows?.length ?? 0}
      emptyTitle="Nothing here yet"
      emptyBody="Characters you open will appear here so you can find your way back to them."
    >
      {(items) => (
        <CardGrid
          items={items.map((row) => ({
            key: row.name,
            href: `/character/${encodeURIComponent(row.name)}`,
            image: row.image ? getImageUrl(row.image) : '',
            title: row.name,
            subtitle: `${relativeDay(row.last_viewed)} · ${row.images} images`,
          }))}
        />
      )}
    </ListTab>
  )
}

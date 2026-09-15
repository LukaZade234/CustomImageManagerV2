import FilterBar from '../../components/FilterBar'
import { Badge, Button, Card, EmptyState } from '../../components/ui'
import { byAsc, byText, useFilteredList } from '../profile/useFilteredList'

/**
 * The master pane: every contributor, with the counts the detail will show.
 *
 * The whole list is already loaded and bounded by people who have written
 * something, which is exactly the case `useFilteredList` exists for — so the
 * search, sort and order are done in memory rather than as another request. The
 * filter bar's mode is omitted: there is no Name/Series choice to make here.
 */

const SORTS = {
  added: { label: 'Most added', compare: byAsc('added'), order: 'desc' },
  removed: { label: 'Most removed', compare: byAsc('removed'), order: 'desc' },
  recent: { label: 'Recent activity', compare: byAsc('last_at'), order: 'desc' },
  name: { label: 'Name', compare: byText('handle'), order: 'asc' },
}
const FIELDS = ['handle']

const SKELETON = [0, 1, 2, 3, 4, 5]

export default function UserList({ users, loading, error, selectedRef, onSelect, onRetry }) {
  const filter = useFilteredList(loading ? null : users, FIELDS, SORTS)
  const items = filter.items ?? []

  return (
    <div className="moderation-users">
      <FilterBar
        query={filter.query}
        onQuery={filter.setQuery}
        placeholder="Search contributors..."
        ariaLabel="Search contributors"
        sortOptions={filter.options}
        sort={filter.sort}
        onSort={filter.setSort}
        order={filter.order}
        onOrder={filter.setOrder}
      />

      {error ? (
        <EmptyState
          title="Could not load contributors"
          description={error}
          action={<Button onClick={onRetry}>Try again</Button>}
        />
      ) : filter.items === null ? (
        <div className="moderation-users__list" role="status" aria-busy="true">
          <span className="sr-only">Loading contributors…</span>
          {SKELETON.map((i) => (
            <div key={i} className="moderation-user moderation-user--skeleton" aria-hidden />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title={filter.filteredToNothing ? 'Nothing matches that' : 'No contributors yet'}
          description={
            filter.filteredToNothing
              ? `No contributor matches “${filter.query}”.`
              : 'Nobody has added or removed an image yet.'
          }
        />
      ) : (
        <ul className="moderation-users__list">
          {items.map((user) => (
            <li key={user.ref}>
              <Card
                as="button"
                type="button"
                padding="sm"
                className={`moderation-user ${user.ref === selectedRef ? 'is-selected' : ''}`}
                aria-pressed={user.ref === selectedRef}
                onClick={() => onSelect(user.ref)}
              >
                <span className="moderation-user__name">
                  {user.handle}
                  {user.role !== 'user' && <Badge tone="neutral">{user.role}</Badge>}
                </span>
                <span className="moderation-user__counts tabular">
                  {user.added} added · {user.removed} removed
                </span>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

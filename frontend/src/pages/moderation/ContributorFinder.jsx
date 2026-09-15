import { useId, useMemo, useState } from 'react'

import { Badge, Button, Card, EmptyState, Input, Select } from '../../components/ui'
import { byAsc, byText, useFilteredList } from '../profile/useFilteredList'

/**
 * The moderation entry point: find a contributor.
 *
 * It used to be a narrow master pane beside a detail column, with a search that
 * only matched the handle. The page opens on this now — one prominent search,
 * a row of facets, and the (bounded) contributor list beneath it, narrowing as
 * you type or filter. The whole list is already loaded, so this is all in
 * memory; selecting someone swaps the whole page for their Info / Images tabs.
 *
 * The facets answer the questions worth asking before picking a name: are they
 * staff, do they have a Discord account (so a ban would mean something), and
 * have they ever removed anything (the ones most likely to need a look).
 */

const SORTS = {
  added: { label: 'Most added', compare: byAsc('added'), order: 'desc' },
  removed: { label: 'Most removed', compare: byAsc('removed'), order: 'desc' },
  recent: { label: 'Recent activity', compare: byAsc('last_at'), order: 'desc' },
  joined: { label: 'Newest accounts', compare: byAsc('created_at'), order: 'desc' },
  name: { label: 'Name', compare: byText('handle'), order: 'asc' },
}
const FIELDS = ['handle']

const ROLE_OPTIONS = [
  { value: 'all', label: 'Everyone' },
  { value: 'staff', label: 'Staff only' },
]
const ACCOUNT_OPTIONS = [
  { value: 'all', label: 'Anyone' },
  { value: 'discord', label: 'Discord only' },
]
const REMOVALS_OPTIONS = [
  { value: 'all', label: 'Any activity' },
  { value: 'removals', label: 'Has removals' },
]

const SKELETON = [0, 1, 2, 3, 4, 5]

/** A labelled facet. The label is programmatically tied to the select, so the
 *  visible word is what a screen reader announces, not a second aria-label. */
function Facet({ label, children }) {
  const id = useId()
  return (
    <div className="moderation-facet">
      <label className="moderation-facet__label text-meta" htmlFor={id}>
        {label}
      </label>
      {children(id)}
    </div>
  )
}

function Options({ options }) {
  return options.map((option) => (
    <option key={option.value} value={option.value}>
      {option.label}
    </option>
  ))
}

export default function ContributorFinder({ users, loading, error, onSelect, onRetry }) {
  const [role, setRole] = useState('all')
  const [account, setAccount] = useState('all')
  const [removals, setRemovals] = useState('all')

  const scoped = useMemo(
    () =>
      (users ?? []).filter(
        (user) =>
          (role === 'all' || user.role !== 'user') &&
          (account === 'all' || user.signed_in) &&
          (removals === 'all' || user.removed > 0),
      ),
    [users, role, account, removals],
  )

  const filter = useFilteredList(loading ? null : scoped, FIELDS, SORTS)
  const items = filter.items ?? []
  const facetting = role !== 'all' || account !== 'all' || removals !== 'all'
  // Nothing to show because the facets excluded everyone, rather than because
  // there is nobody at all.
  const facetsExcluded = facetting && (users?.length ?? 0) > 0 && scoped.length === 0

  return (
    <div className="moderation-finder">
      <div className="moderation-finder__search">
        <Input
          type="search"
          className="moderation-finder__input"
          value={filter.query}
          onChange={(e) => filter.setQuery(e.target.value)}
          placeholder="Search contributors by name"
          aria-label="Search contributors by name"
          autoComplete="off"
        />
        <div className="moderation-finder__filters">
          <Facet label="Sort">
            {(id) => (
              <Select id={id} value={filter.sort} onChange={(e) => filter.setSort(e.target.value)}>
                <Options options={filter.options} />
              </Select>
            )}
          </Facet>
          <Facet label="Role">
            {(id) => (
              <Select id={id} value={role} onChange={(e) => setRole(e.target.value)}>
                <Options options={ROLE_OPTIONS} />
              </Select>
            )}
          </Facet>
          <Facet label="Account">
            {(id) => (
              <Select id={id} value={account} onChange={(e) => setAccount(e.target.value)}>
                <Options options={ACCOUNT_OPTIONS} />
              </Select>
            )}
          </Facet>
          <Facet label="History">
            {(id) => (
              <Select id={id} value={removals} onChange={(e) => setRemovals(e.target.value)}>
                <Options options={REMOVALS_OPTIONS} />
              </Select>
            )}
          </Facet>
        </div>
      </div>

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
              : facetsExcluded
                ? 'No contributor matches these filters.'
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
                className="moderation-user"
                onClick={() => onSelect(user.ref)}
              >
                <span className="moderation-user__name">
                  {user.handle}
                  {user.role !== 'user' && <Badge tone="neutral">{user.role}</Badge>}
                  {user.signed_in && <Badge tone="neutral">Discord</Badge>}
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

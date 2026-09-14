import { Card, EmptyState } from '../../components/ui'
import ListControls from './ListControls'

/** Placeholder count: enough to fill a desktop grid and most of a phone. */
const SKELETON = [0, 1, 2, 3, 4, 5, 6, 7]

/**
 * The shell every profile list shares: heading, blurb, controls, and the three
 * states a personal list can be in.
 *
 * Those three states are the reason this exists rather than each tab rolling
 * its own. "Nothing here yet" and "your search matched nothing" are different
 * situations needing different words, and the loading state must not be
 * mistaken for either — a list that says "nothing saved" for half a second
 * while it loads is actively misleading. The loading state is the same card
 * grid as the loaded one, so the page keeps its height.
 */
export default function ListTab({
  title,
  blurb,
  searchLabel,
  filter,
  total,
  emptyTitle,
  emptyBody,
  mode,
  onMode,
  modeOptions,
  children,
}) {
  const { items } = filter

  return (
    <Card as="section" padding="lg">
      <h2 className="section-heading">{title}</h2>
      {blurb && <p className="text-meta profile-lead">{blurb}</p>}

      {total > 0 && (
        <ListControls
          label={searchLabel}
          query={filter.query}
          onQuery={filter.setQuery}
          sort={filter.sort}
          onSort={filter.setSort}
          order={filter.order}
          onOrder={filter.setOrder}
          options={filter.options}
          mode={mode}
          onMode={onMode}
          modeOptions={modeOptions}
          shown={items?.length ?? 0}
          total={total}
        />
      )}

      {items === null ? (
        <div className="profile-grid profile-grid--uniform" role="status" aria-busy="true">
          <span className="sr-only">Loading…</span>
          {SKELETON.map((i) => (
            <div key={i} className="profile-card profile-card--skeleton" aria-hidden />
          ))}
        </div>
      ) : filter.filteredToNothing ? (
        <EmptyState
          title="Nothing matches that"
          description={`No results for “${filter.query}”. Clear the search to see all ${total}.`}
        />
      ) : items.length === 0 ? (
        <EmptyState title={emptyTitle} description={emptyBody} />
      ) : (
        children(items)
      )}
    </Card>
  )
}

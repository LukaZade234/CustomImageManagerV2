import { useEffect, useState } from 'react'
import { getImageUrl } from '../../api'
import { Button, EmptyState, Input, SegmentedControl } from '../../components/ui'
import { apiUrl } from '../../config'
import CardGrid, { cardRatio } from '../profile/CardGrid'

/**
 * The detail pane: one contributor's additions or removals, newest first.
 *
 * The grid is `profile/CardGrid` in its justified mode, so these cards are the
 * same cards the Hidden and Removed profile tabs render. Every card links to the
 * character page, which is where the acting verbs live — nothing here mutates.
 */

const SKELETON = [0, 1, 2, 3, 4, 5, 6, 7]

export default function UserDetail({
  userRef,
  user,
  state,
  character,
  page,
  data,
  loading,
  error,
  onState,
  onCharacter,
  onPage,
  onRetry,
}) {
  // The character box is local and debounced so typing does not refetch every
  // keystroke; the URL is the source of truth once applied.
  const [draft, setDraft] = useState(character)
  useEffect(() => setDraft(character), [character])
  useEffect(() => {
    const timer = setTimeout(() => {
      if (draft.trim() !== character) onCharacter(draft.trim())
    }, 250)
    return () => clearTimeout(timer)
  }, [draft, character, onCharacter])

  if (!userRef) {
    return (
      <div className="moderation-detail">
        <EmptyState
          title="Pick a contributor"
          description="Pick a contributor to see what they added and removed."
        />
      </div>
    )
  }

  const added = data?.added ?? user?.added ?? 0
  const removed = data?.removed ?? user?.removed ?? 0
  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1

  const cards = items.map((row) => ({
    key: row.id,
    href: `/character/${encodeURIComponent(row.character)}`,
    image: row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url),
    title: row.character,
    subtitle: row.removed_reason || '',
    ratio: cardRatio(row.width, row.height),
  }))

  return (
    <div className="moderation-detail">
      <div className="moderation-detail__header">
        <h2 className="section-heading">{user?.handle ?? 'Contributor'}</h2>
        <SegmentedControl
          name="moderation-state"
          label="Show"
          value={state}
          onChange={onState}
          options={[
            { value: 'active', label: `Added ${added}` },
            { value: 'removed', label: `Removed ${removed}` },
          ]}
        />
        <div className="moderation-detail__filter">
          <Input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="Filter by character..."
            aria-label="Filter by character"
            autoComplete="off"
          />
        </div>
      </div>

      {error ? (
        <EmptyState
          title="Could not load this contributor"
          description={error}
          action={<Button onClick={onRetry}>Try again</Button>}
        />
      ) : loading && !data ? (
        <div className="profile-grid" role="status" aria-busy="true">
          <span className="sr-only">Loading images…</span>
          {SKELETON.map((i) => (
            <div key={i} className="profile-card profile-card--skeleton" aria-hidden />
          ))}
        </div>
      ) : items.length === 0 ? (
        character ? (
          <EmptyState
            title="Nothing matches that character"
            description={`No ${state === 'removed' ? 'removed' : 'added'} images for “${character}”.`}
          />
        ) : (
          <EmptyState
            title={state === 'removed' ? 'Nothing removed' : 'Nothing added'}
            description={
              state === 'removed'
                ? 'This contributor has not removed any images.'
                : 'This contributor has no active images.'
            }
          />
        )
      ) : (
        <div className={loading ? 'is-refetching' : undefined}>
          <CardGrid items={cards} />
        </div>
      )}

      {!error && totalPages > 1 && (
        <div className="customs-pagination">
          <Button
            variant="secondary"
            aria-label="First page"
            onClick={() => onPage(1)}
            disabled={page <= 1}
          >
            «
          </Button>
          <Button
            variant="secondary"
            aria-label="Previous page"
            onClick={() => onPage(Math.max(1, page - 1))}
            disabled={page <= 1}
          >
            ‹
          </Button>
          <span className="pagination-info">
            Page {page} of {totalPages}
          </span>
          <Button
            variant="secondary"
            aria-label="Next page"
            onClick={() => onPage(Math.min(totalPages, page + 1))}
            disabled={page >= totalPages}
          >
            ›
          </Button>
          <Button
            variant="secondary"
            aria-label="Last page"
            onClick={() => onPage(totalPages)}
            disabled={page >= totalPages}
          >
            »
          </Button>
        </div>
      )}
    </div>
  )
}

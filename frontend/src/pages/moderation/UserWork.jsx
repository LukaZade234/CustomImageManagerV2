import { useEffect, useState } from 'react'
import { getImageUrl, getPortraitUrl } from '../../api'
import { Button, EmptyState, Input, SegmentedControl } from '../../components/ui'
import { apiUrl } from '../../config'
import CardGrid, { cardRatio } from '../profile/CardGrid'

/**
 * One contributor's work, in two views.
 *
 * **Images** is the gallery grid — the same cards the Hidden and Removed profile
 * tabs use — with the per-image verbs (restore, permanent delete) attached to
 * each. **Characters** groups the same work by character and sorts it with the
 * Browse Customs vocabulary, which is the "where is it concentrated" answer the
 * image grid cannot give.
 *
 * The verbs are inert in phase 1: rendered so the layout is real, wired later.
 * Nothing here mutates anything yet.
 */
const SKELETON = [0, 1, 2, 3, 4, 5, 6, 7]

const SORT_OPTIONS = [
  { value: 'count', label: 'Most images' },
  { value: 'rank', label: 'Rank' },
  { value: 'name', label: 'Name' },
  { value: 'recent', label: 'Recent' },
]

/** Counter-clockwise arrow: put it back. */
function RestoreIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
    </svg>
  )
}

/** Trash: gone, not just hidden. */
function DeleteIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M3 6h18" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6" />
      <path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
      <line x1="10" y1="11" x2="10" y2="17" />
      <line x1="14" y1="11" x2="14" y2="17" />
    </svg>
  )
}

/**
 * The per-image verbs. Inert in phase 1. Permanent delete will require a second
 * confirm before it ever does anything — it is the app's first irreversible
 * action (it removes the file from ImgChest too), so a single click must not
 * reach it. See docs/MODERATION.md, later phases.
 */
const IMAGE_INERT_ACTIONS = (state) => [
  ...(state === 'removed'
    ? [{ label: 'Restore', icon: <RestoreIcon />, disabled: true, title: 'Not wired up yet' }]
    : []),
  {
    label: 'Delete permanently',
    icon: <DeleteIcon />,
    variant: 'danger',
    disabled: true,
    title: 'Not wired up yet — this will ask you to confirm',
  },
]
function Pagination({ page, totalPages, onPage }) {
  if (totalPages <= 1) return null
  return (
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
  )
}

export default function UserWork({
  view,
  state,
  character,
  sort,
  page,
  images,
  characters,
  onView,
  onState,
  onCharacter,
  onSort,
  onPage,
  onShowCharacter,
}) {
  // The character box is local and debounced, so typing does not refetch every
  // keystroke; the URL is the source of truth once the value is applied.
  const [draft, setDraft] = useState(character)
  useEffect(() => setDraft(character), [character])
  useEffect(() => {
    const timer = setTimeout(() => {
      if (draft.trim() !== character) onCharacter(draft.trim())
    }, 250)
    return () => clearTimeout(timer)
  }, [draft, character, onCharacter])

  const active = view === 'characters' ? characters : images
  const data = active.data
  const items = data?.items ?? []
  const totalPages = data?.total_pages ?? 1

  const added = images.data?.added ?? characters.data?.added ?? 0
  const removed = images.data?.removed ?? characters.data?.removed ?? 0

  const imageCards = items.map((row) => ({
    key: row.id,
    href: `/character/${encodeURIComponent(row.character)}`,
    image: row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url),
    title: row.character,
    subtitle: row.removed_reason || '',
    ratio: cardRatio(row.width, row.height),
    actions: IMAGE_INERT_ACTIONS(state),
  }))

  const characterCards = items.map((row) => ({
    key: row.name,
    // A character here is a filter, not a destination: clicking it shows this
    // contributor's images on that character without leaving moderation.
    onClick: () => onShowCharacter(row.name),
    image: getPortraitUrl(row.image, row.image_thumb),
    title: row.name,
    subtitle: [
      row.series,
      row.rank ? `#${row.rank}` : '',
      `${row.count} image${row.count === 1 ? '' : 's'}`,
    ]
      .filter(Boolean)
      .join(' · '),
  }))

  return (
    <div className="moderation-work">
      <div className="moderation-work__header">
        <SegmentedControl
          name="moderation-view"
          label="View"
          value={view}
          onChange={onView}
          options={[
            { value: 'images', label: 'Images' },
            { value: 'characters', label: 'Characters' },
          ]}
        />
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
        {view === 'characters' && (
          <SegmentedControl
            name="moderation-sort"
            label="Sort"
            value={sort}
            onChange={onSort}
            options={SORT_OPTIONS}
          />
        )}
        <div className="moderation-work__filter">
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

      {active.error ? (
        <EmptyState
          title="Could not load this contributor"
          description={active.error}
          action={<Button onClick={active.refetch}>Try again</Button>}
        />
      ) : active.loading && !data ? (
        <div className="profile-grid" role="status" aria-busy="true">
          <span className="sr-only">Loading…</span>
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
        <div className={active.loading ? 'is-refetching' : undefined}>
          {view === 'characters' ? (
            <CardGrid items={characterCards} uniform />
          ) : (
            <CardGrid items={imageCards} />
          )}
        </div>
      )}

      {!active.error && <Pagination page={page} totalPages={totalPages} onPage={onPage} />}
    </div>
  )
}

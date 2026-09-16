import { Link } from 'react-router-dom'

import { getImageUrl } from '../../api'
import { Button, Card, EmptyState } from '../../components/ui'
import { thumbUrl } from '../../config'
import {
  useModerationDuplicates,
  useRemoveDuplicateImage,
  useRestoreModerationImage,
} from '../../queries/moderation'
import { useStore } from '../../store/useStore'

/**
 * The duplicate audit: pictures the same file was added under more than one URL.
 *
 * The upload gate stops a duplicate *newly* added, but the library predates it,
 * and every fingerprint here was filled in by `scripts/backfill_content_hashes.py`.
 * Removing a copy is a soft delete, restorable from the character's Removed
 * list, so this is a review surface rather than a purge — the same read-only
 * posture as the rest of moderation, with the acting verbs kept to the minimum
 * that makes a finding actionable.
 */

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function DuplicatesPage() {
  const { data, isPending, isError, error, refetch } = useModerationDuplicates()
  const removeImage = useRemoveDuplicateImage()
  const restoreImage = useRestoreModerationImage()
  const addToast = useStore((s) => s.addToast)

  const clusters = data?.clusters ?? []
  const busyUrl = removeImage.isPending
    ? removeImage.variables?.url
    : restoreImage.isPending
      ? restoreImage.variables?.url
      : null

  const remove = (image) =>
    removeImage.mutate(
      { character: image.character, url: image.url },
      {
        onSuccess: () => addToast('Image removed', 'success'),
        onError: (err) => addToast(err.message, 'error'),
      },
    )

  const restore = (image) =>
    restoreImage.mutate(
      { character: image.character, url: image.url },
      {
        onSuccess: () => addToast('Image restored', 'success'),
        onError: (err) => addToast(err.message, 'error'),
      },
    )

  return (
    <>
      <h2 className="section-heading">Duplicate images</h2>
      <p className="text-meta moderation-lead">
        A character holding the same picture twice. The same file on <em>different</em> characters
        is usually intentional — one image can show several of them — so it is not flagged. Removing
        a copy is a soft delete, restorable from the character&rsquo;s Removed list. Existing
        duplicates get a fingerprint from the backfill; new ones are stopped at upload.
      </p>

      {isPending ? (
        <p className="text-meta" role="status">
          Loading…
        </p>
      ) : isError ? (
        <EmptyState
          title="Could not load duplicates"
          description={error?.message || 'Something went wrong.'}
          action={<Button onClick={refetch}>Try again</Button>}
        />
      ) : clusters.length === 0 ? (
        <EmptyState
          title="No duplicates"
          description="No character holds the same picture twice. New duplicates are refused at upload."
        />
      ) : (
        <ul className="duplicates__list">
          {clusters.map((cluster) => (
            <li key={`${cluster.character}:${cluster.hash}`}>
              <Card className="duplicates__cluster">
                <div className="duplicates__head">
                  <h2 className="duplicates__count">
                    <Link
                      to={`/character/${encodeURIComponent(cluster.character)}`}
                      className="duplicates__character"
                    >
                      {cluster.character}
                    </Link>{' '}
                    <span className="duplicates__count-label">{cluster.count} copies</span>
                  </h2>
                  <span className="duplicates__hash" title={cluster.hash}>
                    {cluster.hash.slice(0, 12)}
                  </span>
                </div>
                <ul className="duplicates__images">
                  {cluster.images.map((image) => (
                    <li key={image.id} className="duplicates__image">
                      <Link
                        to={`/character/${encodeURIComponent(image.character)}`}
                        className="duplicates__thumb-link"
                        aria-label={`Open ${image.character}`}
                      >
                        <img
                          className="duplicates__thumb"
                          src={image.thumb ? thumbUrl(image.thumb) : getImageUrl(image.url)}
                          alt=""
                          loading="lazy"
                        />
                      </Link>
                      <div className="duplicates__meta">
                        <span className="text-meta">
                          {image.state === 'removed' ? 'Removed' : 'Active'}
                          {image.owner ? ` · ${image.owner}` : ''}
                          {image.added_at ? ` · ${formatDate(image.added_at)}` : ''}
                        </span>
                      </div>
                      {image.state === 'removed' ? (
                        <Button
                          size="sm"
                          loading={busyUrl === image.url}
                          onClick={() => restore(image)}
                        >
                          Restore
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="danger"
                          loading={busyUrl === image.url}
                          onClick={() => remove(image)}
                        >
                          Remove
                        </Button>
                      )}
                    </li>
                  ))}
                </ul>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

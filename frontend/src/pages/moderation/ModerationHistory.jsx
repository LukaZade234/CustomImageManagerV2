import { Badge, Button } from '../../components/ui'
import { moderationAction } from '../../utils/moderationActions'

/**
 * Everything staff have sent this contributor, newest first.
 *
 * This is the durable record, not the inbox: a warning the recipient has
 * dismissed still shows here. Moderators read it; only the owner gets a Delete
 * (the backend enforces that regardless), and deleting takes the delivered
 * message with it.
 */

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function ModerationHistory({
  items = [],
  loading = false,
  error = null,
  onRetry,
  canDelete = false,
  onDelete,
}) {
  return (
    <section className="moderation-history" aria-labelledby="moderation-history-heading">
      <div className="moderation-history__head">
        <h2 className="section-heading" id="moderation-history-heading">
          Moderation history
        </h2>
        {!loading && !error && items.length > 0 && (
          <span className="text-meta tabular">{items.length}</span>
        )}
      </div>

      {error ? (
        <p className="text-meta" role="status">
          Could not load the moderation history.{' '}
          <Button size="sm" variant="ghost" onClick={onRetry}>
            Try again
          </Button>
        </p>
      ) : loading ? (
        <p className="text-meta" role="status">
          Loading…
        </p>
      ) : items.length === 0 ? (
        <p className="moderation-history__empty text-meta">No moderation messages yet.</p>
      ) : (
        <ol className="moderation-history__list">
          {items.map((entry) => {
            const meta = moderationAction(entry.action) ?? {
              label: entry.action,
              tone: 'neutral',
            }
            return (
              <li key={entry.id} className="moderation-message">
                <div className="moderation-message__head">
                  <h3 className={`moderation-message__title moderation-severity--${meta.tone}`}>
                    {entry.title}
                    <Badge tone={meta.tone}>{meta.label}</Badge>
                  </h3>
                  <span className="moderation-message__meta text-meta">
                    {entry.actor_handle ? `by ${entry.actor_handle} · ` : ''}
                    {formatDate(entry.created_at)}
                  </span>
                </div>
                {entry.body && <p className="moderation-message__body">{entry.body}</p>}
                {canDelete && (
                  <div className="moderation-message__actions">
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => onDelete(entry)}
                      title="Remove this record, and the message it sent"
                    >
                      Delete
                    </Button>
                  </div>
                )}
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

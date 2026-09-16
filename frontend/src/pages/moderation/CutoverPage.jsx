import { Badge, Button, Card, EmptyState } from '../../components/ui'
import { useModerationCutover } from '../../queries/moderation'

/**
 * The ImgChest cut-over preview, owner-only.
 *
 * This page renders what `scripts/imgchest_cleanup.py` wrote; it never deletes
 * anything itself. The script is the destructive half precisely so a mistake
 * here cannot remove an image. The job of this page is to let the operator look
 * at the two lists — what would be permanently deleted, and what would be
 * recovered into the Removed drawer — and decide whether to run the script.
 *
 * Flat lists with counts, not grouped by character: the operator is scanning for
 * a surprise (an image they know is in use, or one whose loss would be noticed),
 * and a name-first layout is easier to scan for that than a grouped one.
 */

function formatStamp(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function fileIdFromUrl(url) {
  const match = /cdn\.imgchest\.com\/files\/([A-Za-z0-9]+)/.exec(url || '')
  return match ? match[1] : url
}

export default function CutoverPage() {
  const { data, isPending, isError, error, refetch, isFetching } = useModerationCutover()

  if (isPending) {
    return (
      <>
        <h2 className="section-heading">Cut-over</h2>
        <p className="text-meta" role="status">
          Loading…
        </p>
      </>
    )
  }

  if (isError) {
    return (
      <>
        <h2 className="section-heading">Cut-over</h2>
        <EmptyState
          title="Could not load the preview"
          description={error?.message || 'Something went wrong.'}
          action={<Button onClick={refetch}>Try again</Button>}
        />
      </>
    )
  }

  if (!data?.available) {
    return (
      <>
        <h2 className="section-heading">Cut-over</h2>
        <p className="text-meta moderation-lead">
          Reconcile the ImgChest account against what is actually in use. This page shows the
          preview only — deletion is done by the script, by hand, after this preview is read.
        </p>
        <EmptyState
          title="No preview yet"
          description="Run scripts/imgchest_cleanup.py to write one, then come back here. Nothing has been deleted."
        />
      </>
    )
  }

  const preview = data.preview
  const counts = preview.counts ?? {}
  const toDelete = preview.delete ?? []
  const toRecover = preview.recover ?? []
  const warnings = preview.warnings ?? []
  const malformed = preview.export?.malformed ?? []
  const malformedTotal = preview.export?.malformed_total ?? malformed.length

  return (
    <>
      <header className="cutover__head">
        <div>
          <h2 className="section-heading">Cut-over</h2>
          <p className="text-meta moderation-lead">
            Reconcile the ImgChest account against what is actually in use. Nothing here deletes:
            the script does, by hand, once these lists have been read.
          </p>
        </div>
        <Button onClick={refetch} disabled={isFetching}>
          {isFetching ? 'Refreshing…' : 'Refresh'}
        </Button>
      </header>

      <Card padding="lg" className="cutover__stamp">
        <p className="text-meta">
          Preview generated <strong>{formatStamp(preview.generated_at)}</strong> for the account{' '}
          <strong>{preview.account}</strong>.
          {preview.executed
            ? ` It has since been run: ${preview.deleted} deleted, ${preview.recovered} recovered.`
            : ' It has not been run.'}
        </p>
        <p className="text-meta">
          Export: {preview.export?.unique_urls ?? 0} unique in-use URLs
          {malformedTotal ? `, ${malformedTotal} unreadable lines` : ''}.
        </p>
      </Card>

      <div className="cutover__counts">
        <Card className="cutover__count">
          <span className="cutover__count-value">{counts.keepers ?? 0}</span>
          <span className="text-meta">kept (in use, or on the site)</span>
        </Card>
        <Card className="cutover__count">
          <span className="cutover__count-value">{counts.delete_candidates ?? 0}</span>
          <span className="text-meta">to delete permanently</span>
        </Card>
        <Card className="cutover__count">
          <span className="cutover__count-value">{counts.recoverable ?? 0}</span>
          <span className="text-meta">to recover into Removed</span>
        </Card>
        {warnings.length > 0 && (
          <Card className="cutover__count cutover__count--warn">
            <span className="cutover__count-value">{warnings.length}</span>
            <span className="text-meta">posts this pass cannot fully resolve</span>
          </Card>
        )}
      </div>

      {malformed.length > 0 && (
        <Card padding="lg" className="cutover__warning">
          <h3 className="cutover__section-title">
            Unreadable export lines <Badge tone="warning">{malformedTotal}</Badge>
          </h3>
          <p className="text-meta">
            These lines did not parse as <code>Name - URL</code> and were ignored. If any of them is
            real in-use content, fix the export and re-run before executing.
          </p>
          <ul className="cutover__lines">
            {malformed.map((line) => (
              <li key={line} className="cutover__line">
                {line}
              </li>
            ))}
          </ul>
        </Card>
      )}

      {warnings.length > 0 && (
        <Card padding="lg" className="cutover__warning">
          <h3 className="cutover__section-title">
            Multi-image posts <Badge tone="caution">{warnings.length}</Badge>
          </h3>
          <p className="text-meta">
            The listing exposes only a post's first image, so these could not be fully planned.
            Check them by hand before executing.
          </p>
          <ul className="cutover__lines">
            {warnings.map((warning) => (
              <li key={`${warning.post_id}:${warning.detail}`} className="cutover__line">
                <code>{warning.post_id}</code> — {warning.detail}
              </li>
            ))}
          </ul>
        </Card>
      )}

      <section className="cutover__section">
        <h3 className="cutover__section-title">
          Will be permanently deleted <Badge tone="danger">{toDelete.length}</Badge>
        </h3>
        <p className="text-meta">
          In neither the Discord export nor the database. Nothing here is recoverable after the
          script runs.
        </p>
        {toDelete.length === 0 ? (
          <EmptyState title="Nothing to delete" description="Every ImgChest file is a keeper." />
        ) : (
          <ul className="cutover__lines">
            {toDelete.map((item) => (
              <li key={item.file_id} className="cutover__line">
                <code>{item.file_id}</code>
                {item.image_count > 1 ? ` (post ${item.post_id}, ${item.image_count} images)` : ''}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="cutover__section">
        <h3 className="cutover__section-title">
          Will be recovered into Removed <Badge tone="accent">{toRecover.length}</Badge>
        </h3>
        <p className="text-meta">
          In use in Discord, but missing from the site. The script re-adds these in the Removed
          state so staff can restore them.
        </p>
        {toRecover.length === 0 ? (
          <EmptyState
            title="Nothing to recover"
            description="Every in-use image is already on the site."
          />
        ) : (
          <ul className="cutover__lines">
            {toRecover.map((item) => (
              <li key={item.url} className="cutover__line">
                <strong>{item.character}</strong> — <code>{fileIdFromUrl(item.url)}</code>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

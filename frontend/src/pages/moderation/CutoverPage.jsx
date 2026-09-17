import { useState } from 'react'
import { Badge, Button, Card, EmptyState, SegmentedControl } from '../../components/ui'
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
 * Images rather than ids: the decision this page exists for is "do I recognise
 * this picture, and would its loss be noticed", and a file id cannot answer
 * that. The id stays under each one for cross-referencing with the script's
 * output.
 *
 * The host filter exists because the export is Discord's, not the app's. It
 * contains images from other people's hosts — the app has only ever uploaded to
 * ImgChest — and those are never recoverable here. "App images only" hides that
 * noise; "External only" is there to inspect it.
 */

const HOST_FILTERS = [
  { value: 'app', label: 'App images only', short: 'App' },
  { value: 'all', label: 'Everything', short: 'All' },
  { value: 'external', label: 'External only', short: 'External' },
]

/** True when the app could have made this URL. Only ImgChest is ever uploaded to. */
function isAppUrl(url) {
  return /cdn\.imgchest\.com\/files\//.test(url || '')
}

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

/** One reviewed image: the picture first, its identifiers underneath. */
function ImageTile({ url, caption, note, tone }) {
  return (
    <li className="cutover__tile">
      <a
        className="cutover__tile-frame"
        href={url}
        target="_blank"
        rel="noreferrer noopener"
        title="Open full size in a new tab"
      >
        {/* Decorative: the caption below carries the meaning, and alt text
            repeating a file id helps nobody. */}
        <img src={url} alt="" loading="lazy" />
      </a>
      <span className={`cutover__tile-caption${tone ? ` is-${tone}` : ''}`}>{caption}</span>
      {note ? <span className="cutover__tile-note">{note}</span> : null}
    </li>
  )
}

export default function CutoverPage() {
  const { data, isPending, isError, error, refetch, isFetching } = useModerationCutover()
  const [hostFilter, setHostFilter] = useState('app')

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
  const warnings = preview.warnings ?? []
  const malformed = preview.export?.malformed ?? []
  const malformedTotal = preview.export?.malformed_total ?? malformed.length

  // The script splits these already: `recover` is only URLs the app could have
  // made, `foreign` is everything else from the export. Older previews have no
  // `foreign` key, so fall back to classifying by host.
  const recoverAll = preview.recover ?? []
  const externalAll = preview.foreign ?? recoverAll.filter((item) => !isAppUrl(item.url))
  const recoverApp = recoverAll.filter((item) => isAppUrl(item.url))

  const showExternal = hostFilter === 'external'
  const toRecover = showExternal ? externalAll : recoverApp
  // The delete list is always the account's own posts, so the host filter does
  // not apply to it. It is shown under both non-external views because it is the
  // irreversible half and hiding it would be the wrong default.
  const toDelete = showExternal ? [] : (preview.delete ?? [])

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

      <Card padding="lg" className="cutover__filter">
        <SegmentedControl
          name="cutover-host-filter"
          label="Which images to show"
          value={hostFilter}
          onChange={setHostFilter}
          options={HOST_FILTERS}
        />
        <p className="text-meta">
          {hostFilter === 'app' &&
            `Only ImgChest URLs, which are the ones this app could have made — ` +
              `${recoverApp.length} to recover.`}
          {hostFilter === 'external' &&
            `${externalAll.length} external URL(s) from the export. These are hosted by ` +
              `somebody else, so they are never recovered and never deleted here.`}
          {hostFilter === 'all' && `Everything the export named, app and external together.`}
        </p>
      </Card>

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

      {!showExternal && (
        <section className="cutover__section">
          <h3 className="cutover__section-title">
            Will be permanently deleted <Badge tone="danger">{toDelete.length}</Badge>
          </h3>
          <p className="text-meta">
            On the ImgChest account, in neither the Discord export nor the database. Nothing here is
            recoverable after the script runs. These are always this account's own uploads, so the
            host filter does not apply to them.
          </p>
          {toDelete.length === 0 ? (
            <EmptyState title="Nothing to delete" description="Every ImgChest file is a keeper." />
          ) : (
            <ul className="cutover__grid">
              {toDelete.map((item) => (
                <ImageTile
                  key={item.file_id}
                  url={item.url || `https://cdn.imgchest.com/files/${item.file_id}.png`}
                  caption={item.file_id}
                  tone="danger"
                  note={item.image_count > 1 ? `post has ${item.image_count} images` : undefined}
                />
              ))}
            </ul>
          )}
        </section>
      )}

      <section className="cutover__section">
        <h3 className="cutover__section-title">
          {showExternal ? 'External URLs (never touched)' : 'Will be recovered into Removed'}{' '}
          <Badge tone={showExternal ? 'caution' : 'accent'}>{toRecover.length}</Badge>
        </h3>
        <p className="text-meta">
          {showExternal
            ? 'Used in Discord but hosted elsewhere. Recovering these would put another person\u2019s upload on the site under a row that could never be permanently deleted from here, so they are listed for review only.'
            : 'In use in Discord, missing from the site, and hostable by this app. The script re-adds these in the Removed state so staff can restore them.'}
        </p>
        {toRecover.length === 0 ? (
          <EmptyState
            title={showExternal ? 'No external URLs' : 'Nothing to recover'}
            description={
              showExternal
                ? 'Every URL in the export is one this app could have made.'
                : 'Every in-use app image is already on the site.'
            }
          />
        ) : (
          <ul className="cutover__grid">
            {toRecover.map((item) => (
              <ImageTile
                key={item.url}
                url={item.url}
                caption={item.character || '—'}
                tone={showExternal ? 'caution' : undefined}
                note={fileIdFromUrl(item.url)}
              />
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

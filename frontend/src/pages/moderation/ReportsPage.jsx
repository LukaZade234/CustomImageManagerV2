import { useState } from 'react'
import { Link } from 'react-router-dom'

import { getImageUrl } from '../../api'
import { Button, Card, EmptyState, SegmentedControl } from '../../components/ui'
import { thumbUrl } from '../../config'
import { useModerationReports } from '../../queries/moderation'

/**
 * Reported images, split by whether the report threshold has acted.
 *
 * Two distinct reports remove an image (`DECISIONS.md` §1), so there are really
 * two questions here: what is still live and reported, and what the threshold
 * already took down. The filter is that split, not a severity or a date range.
 *
 * Read-only, deliberately: reporting already acts, and the verbs to restore or
 * delete an image stay where the image and its context are — the character page,
 * or the Duplicates tab for a duplicate. This page answers "what has been
 * reported, and what happened".
 */

const REASON_LABELS = {
  wrong_character: 'Wrong character',
  dead_link: 'Broken image',
  nsfw: 'NSFW',
  duplicate: 'Duplicate',
  ai_artwork: 'AI artwork',
}

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export default function ReportsPage() {
  const [status, setStatus] = useState('reported')
  const { data, isPending, isError, error, refetch } = useModerationReports(status)

  const counts = data?.counts ?? { reported: 0, removed: 0 }
  const items = data?.items ?? []

  return (
    <>
      <h2 className="section-heading">Reports</h2>
      <p className="text-meta moderation-lead">
        Images the community reported. Two distinct reports remove an image; the rest are still
        live. Restoring or deleting happens on the character page, or the Duplicates tab for a
        duplicate.
      </p>

      <div className="reports__filters">
        <SegmentedControl
          name="report-status"
          label="Report status"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'reported', label: `Not removed yet (${counts.reported})` },
            { value: 'removed', label: `Removed by reports (${counts.removed})` },
          ]}
        />
      </div>

      {isPending ? (
        <p className="text-meta" role="status">
          Loading…
        </p>
      ) : isError ? (
        <EmptyState
          title="Could not load reports"
          description={error?.message || 'Something went wrong.'}
          action={<Button onClick={refetch}>Try again</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title={status === 'removed' ? 'Nothing removed by reports' : 'No open reports'}
          description={
            status === 'removed'
              ? 'No image has been taken down by the report threshold.'
              : 'Nobody has reported an image that is still live.'
          }
        />
      ) : (
        <ul className="reports__list">
          {items.map((item) => (
            <li key={item.id}>
              <Card className="reports__item">
                <Link
                  to={`/character/${encodeURIComponent(item.character)}`}
                  className="reports__thumb-link"
                  aria-label={`Open ${item.character}`}
                >
                  <img
                    className="reports__thumb"
                    src={item.thumb ? thumbUrl(item.thumb) : getImageUrl(item.url)}
                    alt=""
                    loading="lazy"
                  />
                </Link>
                <div className="reports__body">
                  <div className="reports__head">
                    <Link
                      to={`/character/${encodeURIComponent(item.character)}`}
                      className="reports__character"
                    >
                      {item.character}
                    </Link>
                    <span className={`reports__state reports__state--${item.state}`}>
                      {item.state === 'removed' ? 'Removed' : 'Reported'}
                    </span>
                  </div>
                  <p className="text-meta">
                    {item.report_count} {item.report_count === 1 ? 'report' : 'reports'}
                    {item.state === 'removed' && item.removed_at
                      ? ` · removed ${formatDate(item.removed_at)}`
                      : ` · last ${formatDate(item.last_report_at)}`}
                  </p>
                  <ul className="reports__reports">
                    {item.reports.map((report) => (
                      <li
                        key={`${report.reason}:${report.reporter ?? ''}:${report.at ?? ''}`}
                        className="text-meta"
                      >
                        <strong>{REASON_LABELS[report.reason] ?? report.reason}</strong>
                        {report.reporter ? ` — ${report.reporter}` : ''}
                        {report.at ? ` · ${formatDate(report.at)}` : ''}
                      </li>
                    ))}
                  </ul>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

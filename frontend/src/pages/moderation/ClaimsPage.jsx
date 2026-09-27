import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'

import {
  Button,
  Card,
  ConfirmDialog,
  EmptyState,
  Field,
  Input,
  SegmentedControl,
} from '../../components/ui'
import {
  useApproveAllModerationClaims,
  useDecideModerationClaim,
  useModerationClaims,
} from '../../queries/moderation'

/**
 * Ownership claims: requests to be given a character's unowned images.
 *
 * The unowned bucket is the v1 import, and the design makes it permanent on
 * purpose (migration 004, DECISIONS.md §1). Migration 025 is the one bounded way
 * back out, for the original userbase, and this page is where a moderator grants
 * it. Unlike the rest of this surface, this page *acts* — the transfer is the
 * one thing a claimant cannot do for themselves.
 *
 * Two filters, as asked for: by character and by user, each matching part of
 * the name. When the user filter narrows the list to one person, the page also
 * offers the bulk approve, for the common case where someone obviously owns a
 * run of characters and approving them one at a time is busywork.
 */

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function ClaimItem({ item, onDecide, busy }) {
  const [rejecting, setRejecting] = useState(false)
  const [reason, setReason] = useState('')
  const [approving, setApproving] = useState(false)

  const pending = item.status === 'pending'

  return (
    <Card className="claims__item">
      <div className="claims__head">
        <Link to={`/character/${encodeURIComponent(item.character)}`} className="claims__character">
          {item.character}
        </Link>
        <span className="claims__meta">
          requested by {item.claimant ?? 'an unknown user'}
          {item.created_at ? ` · ${formatDate(item.created_at)}` : ''}
        </span>
      </div>

      <div className="claims__counts text-meta">
        <span>
          {item.unowned_total} unowned {item.unowned_total === 1 ? 'image' : 'images'}
          {item.unowned_active != null
            ? ` (${item.unowned_active} in the gallery, ${item.unowned_total - item.unowned_active} removed)`
            : ''}
        </span>
      </div>

      {!pending && (
        <p className="claims__meta">
          {item.status === 'approved' ? 'Approved' : 'Rejected'}
          {item.decided_at ? ` ${formatDate(item.decided_at)}` : ''}
          {item.decided_by ? ` by ${item.decided_by}` : ''}
          {item.status === 'approved' ? ` · ${item.images_granted} granted` : ''}
          {item.reason ? ` · ${item.reason}` : ''}
        </p>
      )}

      {pending && (
        <div className="claims__actions">
          <Button variant="primary" onClick={() => setApproving(true)} disabled={busy}>
            Approve
          </Button>
          <Button variant="danger" onClick={() => setRejecting(true)} disabled={busy}>
            Reject
          </Button>
        </div>
      )}

      {approving && (
        <ConfirmDialog
          title="Give these images to this user?"
          body={
            <>
              <p>
                This grants every unowned image on <strong>{item.character}</strong> to{' '}
                {item.claimant ?? 'this user'}
                {item.unowned_total ? ` (${item.unowned_total} images)` : ''}.
              </p>
              <p>
                Images already owned by someone else are not affected. Any other pending claim on
                this character is rejected automatically.
              </p>
            </>
          }
          confirmLabel="Approve claim"
          onConfirm={() => {
            setApproving(false)
            onDecide(item.id, true, '')
          }}
          onCancel={() => setApproving(false)}
        />
      )}

      {rejecting && (
        <ConfirmDialog
          title="Reject this claim?"
          body={
            <Field label="Reason (optional)" hint="Sent to the claimant, who may ask again.">
              {({ id, describedBy }) => (
                <Input
                  id={id}
                  aria-describedby={describedBy}
                  className="claims__reason"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. please sign in with your old account"
                />
              )}
            </Field>
          }
          confirmLabel="Reject claim"
          variant="danger"
          onConfirm={() => {
            setRejecting(false)
            onDecide(item.id, false, reason.trim())
          }}
          onCancel={() => {
            setRejecting(false)
            setReason('')
          }}
        />
      )}
    </Card>
  )
}

export default function ClaimsPage() {
  const [status, setStatus] = useState('pending')
  const [character, setCharacter] = useState('')
  const [claimant, setClaimant] = useState('')
  const [draft, setDraft] = useState('')
  const [claimantDraft, setClaimantDraft] = useState('')
  const [bulkConfirm, setBulkConfirm] = useState(false)
  const [bulkMessage, setBulkMessage] = useState('')

  // Both boxes are debounced, matching the contributor work views: typing must
  // not refetch on every keystroke.
  useEffect(() => {
    const timer = setTimeout(() => {
      const next = draft.trim()
      if (next !== character) setCharacter(next)
      const nextClaimant = claimantDraft.trim()
      if (nextClaimant !== claimant) setClaimant(nextClaimant)
    }, 250)
    return () => clearTimeout(timer)
  }, [draft, character, claimantDraft, claimant])

  const { data, isPending, isError, error, refetch } = useModerationClaims({
    status,
    char: character,
    claimant,
  })
  const decide = useDecideModerationClaim()
  const approveAll = useApproveAllModerationClaims()

  const counts = data?.counts ?? { pending: 0, approved: 0, rejected: 0 }
  const items = data?.items ?? []
  const busy = decide.isPending || approveAll.isPending

  const handleDecide = async (claimId, approve, reason) => {
    try {
      await decide.mutateAsync({ claimId, approve, reason })
    } catch {
      // The list refresh is the feedback that matters; react-query surfaces the
      // error state, and a toast here would need the store for one line.
      refetch()
    }
  }

  const handleApproveAll = async () => {
    setBulkConfirm(false)
    if (!bulkUser) return
    try {
      const result = await approveAll.mutateAsync(bulkUser.ref)
      setBulkMessage(
        result.remaining > 0
          ? `Approved ${result.approved_count} claims; ${result.remaining} still pending — run it again.`
          : `Approved ${result.approved_count} claims.`,
      )
    } catch {
      setBulkMessage('Could not approve those claims.')
    }
  }

  // The bulk approve acts on one person, so it is offered only when the user
  // filter has narrowed the list to a single claimant. A partial name such as
  // "a" can match several people, and approving all of them at once is not what
  // anyone typing a name means.
  const refs = new Set(items.map((item) => item.user_ref))
  const bulkUser =
    claimant && refs.size === 1 && items[0].user_ref
      ? { ref: items[0].user_ref, name: items[0].claimant ?? 'this user' }
      : null

  return (
    <>
      <h2 className="section-heading">Claims</h2>
      <p className="text-meta moderation-lead">
        Requests from users to be given a character&apos;s unowned images — the ones imported from
        the old site before ownership was recorded. Approving grants every unowned image on that
        character; images already owned by someone else are never taken.
      </p>

      <div className="claims__filters">
        <SegmentedControl
          name="claim-status"
          label="Claim status"
          value={status}
          onChange={setStatus}
          options={[
            { value: 'pending', label: `Pending (${counts.pending})` },
            { value: 'approved', label: `Approved (${counts.approved})` },
            { value: 'rejected', label: `Rejected (${counts.rejected})` },
          ]}
        />
        <Field label="Character" className="claims__filter">
          {({ id }) => (
            <Input
              id={id}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              placeholder="Filter by character…"
            />
          )}
        </Field>
        <Field label="User" className="claims__filter">
          {({ id }) => (
            <Input
              id={id}
              value={claimantDraft}
              onChange={(e) => {
                setClaimantDraft(e.target.value)
                setBulkMessage('')
              }}
              placeholder="Filter by user…"
            />
          )}
        </Field>
      </div>

      {bulkMessage && (
        <p className="text-meta" role="status">
          {bulkMessage}
        </p>
      )}

      {isPending ? (
        <p className="text-meta" role="status">
          Loading…
        </p>
      ) : isError ? (
        <EmptyState
          title="Could not load claims"
          description={error?.message || 'Something went wrong.'}
          action={<Button onClick={refetch}>Try again</Button>}
        />
      ) : items.length === 0 ? (
        <EmptyState
          title={status === 'pending' ? 'No pending claims' : `No ${status} claims`}
          description={
            character || claimant
              ? 'Nothing matches these filters.'
              : status === 'pending'
                ? 'Nobody is waiting to reclaim a character.'
                : 'Nothing has been decided yet.'
          }
        />
      ) : (
        <>
          <ul className="claims__list">
            {items.map((item) => (
              <li key={item.id}>
                <ClaimItem item={item} onDecide={handleDecide} busy={busy} />
              </li>
            ))}
          </ul>

          {bulkUser && status === 'pending' && (
            <div className="claims__bulk">
              <span className="text-meta">
                Approving every pending claim for {bulkUser.name}, up to the server&apos;s cap.
              </span>
              <Button variant="primary" onClick={() => setBulkConfirm(true)} disabled={busy}>
                Approve all {items.length} for {bulkUser.name}
              </Button>
            </div>
          )}
        </>
      )}

      {bulkConfirm && bulkUser && (
        <ConfirmDialog
          title={`Approve every pending claim for ${bulkUser.name}?`}
          body={
            <>
              <p>
                This approves all {items.length} pending claims currently listed for {bulkUser.name}
                , and grants every unowned image on each of those characters.
              </p>
              <p>
                If more remain than the server will do at once, you will be told to run it again.
              </p>
            </>
          }
          confirmLabel="Approve all"
          onConfirm={handleApproveAll}
          onCancel={() => setBulkConfirm(false)}
        />
      )}
    </>
  )
}

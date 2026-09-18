import { useState } from 'react'

import { Button, Card, ConfirmDialog } from './ui'

/**
 * The banner offering to reclaim a character's unowned images.
 *
 * Shown only while the character still has images with no `added_by` — the v1
 * import, whose ownership was never recorded. Filing a request grants nothing:
 * it asks a moderator, who approves or rejects it in the Claims queue. The
 * copy says so rather than implying an instant result, because a user who
 * thinks they have already got their images back will not understand why the
 * gallery has not changed.
 *
 * This is a temporary reconciliation tool. When the banner disappears, the
 * character has either been claimed or had nothing to claim, and that is the
 * intended end state.
 */
export default function ClaimBanner({ claimable, myClaim, signedIn, onClaim, busy }) {
  const [confirming, setConfirming] = useState(false)

  if (!claimable) return null
  const total = (claimable.active || 0) + (claimable.removed || 0)
  if (total === 0) return null

  // Once approved there is nothing left unowned, so the banner is gone by the
  // time this renders. Pending and rejected both keep it, with different copy.
  const status = myClaim?.status ?? null
  const pending = status === 'pending'

  const count = [
    claimable.active ? `${claimable.active} in the gallery` : null,
    claimable.removed ? `${claimable.removed} in the Removed drawer` : null,
  ]
    .filter(Boolean)
    .join(' and ')

  return (
    <Card as="section" padding="md" className="claim-banner">
      <div className="claim-banner__text">
        <h2 className="claim-banner__title">
          {pending ? 'Your claim is awaiting review' : 'Were these images yours?'}
        </h2>
        {pending ? (
          <p className="claim-banner__body">
            You asked to claim the {total} unowned {total === 1 ? 'image' : 'images'} on this
            character. A moderator will approve or reject it; you will get a notification either
            way.
          </p>
        ) : (
          <p className="claim-banner__body">
            This character has <strong>{total}</strong> unowned {total === 1 ? 'image' : 'images'} (
            {count}), imported from the old site before ownership was recorded. If they are yours,
            you can ask a moderator to give them back.
          </p>
        )}
        {status === 'rejected' && (
          <p className="claim-banner__body claim-banner__body--rejected">
            Your last request was not approved
            {myClaim?.reason ? `: ${myClaim.reason}` : '.'} You can ask again if this looks wrong.
          </p>
        )}
      </div>

      {!pending &&
        (signedIn ? (
          <Button variant="primary" onClick={() => setConfirming(true)} disabled={busy}>
            Claim {total === 1 ? 'this image' : 'these images'}
          </Button>
        ) : (
          // Filing is tied to an account so a ban can stop abuse, so a
          // signed-out visitor is told to sign in rather than given a button
          // that would only 403.
          <p className="claim-banner__body claim-banner__signin">
            Sign in with Discord to file a claim.
          </p>
        ))}

      {confirming && (
        <ConfirmDialog
          title="Ask to claim this character?"
          body={
            <>
              <p>
                A moderator will review your request to be given the {total} unowned{' '}
                {total === 1 ? 'image' : 'images'} on this character.
              </p>
              <p>
                Nothing changes until they approve. Images already owned by someone else are not
                affected.
              </p>
            </>
          }
          confirmLabel="Send request"
          onConfirm={() => {
            setConfirming(false)
            onClaim()
          }}
          onCancel={() => setConfirming(false)}
        />
      )}
    </Card>
  )
}

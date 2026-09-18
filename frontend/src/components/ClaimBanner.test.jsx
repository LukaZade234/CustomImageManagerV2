/**
 * The claim banner on a character page. The one thing it must get right: it is
 * absent when there is nothing to claim, and its button reflects the viewer's
 * claim state rather than offering a request that would be refused.
 */
import { screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { renderWithQueryClient } from '../test/renderWithQueryClient'
import ClaimBanner from './ClaimBanner'

const CLAIMABLE = { active: 3, removed: 2 }

function renderBanner(props = {}) {
  return renderWithQueryClient(
    <ClaimBanner claimable={CLAIMABLE} myClaim={null} signedIn onClaim={() => {}} {...props} />,
  )
}

describe('ClaimBanner', () => {
  it('renders nothing when there is nothing unowned', () => {
    const { container } = renderBanner({ claimable: null })
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when the counts are both zero', () => {
    const { container } = renderBanner({ claimable: { active: 0, removed: 0 } })
    expect(container).toBeEmptyDOMElement()
  })

  it('states how many images are claimable, split by state', () => {
    renderBanner()
    expect(screen.getByText('Were these images yours?')).toBeInTheDocument()
    expect(screen.getByText(/5/)).toBeInTheDocument()
    expect(screen.getByText(/3 in the gallery and 2 in the Removed drawer/)).toBeInTheDocument()
  })

  it('asks a signed-out visitor to sign in instead of offering a button', () => {
    renderBanner({ signedIn: false })
    expect(screen.getByText(/sign in with discord/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument()
  })

  it('confirms before filing, then calls back', async () => {
    const onClaim = vi.fn()
    renderBanner({ onClaim })
    await userEvent.click(screen.getByRole('button', { name: /claim these images/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Send request' }))
    expect(onClaim).toHaveBeenCalledTimes(1)
  })

  it('shows the awaiting-review state once a claim is pending', () => {
    renderBanner({ myClaim: { status: 'pending' } })
    expect(screen.getByText(/awaiting review/i)).toBeInTheDocument()
    // No second request while one is in flight.
    expect(screen.queryByRole('button', { name: /claim/i })).not.toBeInTheDocument()
  })

  it('shows a rejected claim with the reason and offers another try', () => {
    renderBanner({ myClaim: { status: 'rejected', reason: 'Not your account' } })
    expect(screen.getByText(/not approved/i)).toBeInTheDocument()
    expect(screen.getByText(/Not your account/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /claim these images/i })).toBeInTheDocument()
  })
})

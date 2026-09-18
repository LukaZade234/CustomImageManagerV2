/**
 * The ownership-claim queue. The two things it must get right: a decision is
 * sent with the right verb, and the per-user bulk approve appears only when a
 * user filter is actually applied.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listModerationClaims: vi.fn(),
  decideModerationClaim: vi.fn(),
  approveAllModerationClaims: vi.fn(),
}))

vi.mock('../../api', () => ({
  getImageUrl: (p) => p || '',
  apiClient: api,
}))

import { renderWithQueryClient } from '../../test/renderWithQueryClient'
import ClaimsPage from './ClaimsPage'

const PENDING = {
  status: 'pending',
  counts: { pending: 2, approved: 0, rejected: 0 },
  items: [
    {
      id: 10,
      status: 'pending',
      character: 'Rem',
      character_id: 1,
      claimant: 'Ada Otter',
      user_ref: 'ref-ada',
      created_at: '2026-02-01T00:00:00Z',
      decided_at: null,
      decided_by: null,
      reason: '',
      images_granted: 0,
      unowned_total: 5,
      unowned_active: 3,
    },
    {
      id: 11,
      status: 'pending',
      character: 'Ram',
      character_id: 2,
      claimant: 'Ada Otter',
      user_ref: 'ref-ada',
      created_at: '2026-02-02T00:00:00Z',
      decided_at: null,
      decided_by: null,
      reason: '',
      images_granted: 0,
      unowned_total: 2,
      unowned_active: 2,
    },
  ],
  total: 2,
}

function renderPage() {
  return renderWithQueryClient(
    <MemoryRouter>
      <ClaimsPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.listModerationClaims.mockReset().mockResolvedValue(PENDING)
  api.decideModerationClaim.mockReset().mockResolvedValue({ success: true, approved: true })
  api.approveAllModerationClaims
    .mockReset()
    .mockResolvedValue({ success: true, approved_count: 2, images_granted: 7, remaining: 0 })
})

describe('ClaimsPage', () => {
  it('lists pending claims with the character and the claimant', async () => {
    renderPage()
    expect(await screen.findByText('Rem')).toBeInTheDocument()
    expect(screen.getByText('Ram')).toBeInTheDocument()
    expect(api.listModerationClaims).toHaveBeenCalledWith({
      status: 'pending',
      char: '',
      user: '',
      page: 1,
    })
  })

  it('says what an approval would move', async () => {
    renderPage()
    await screen.findByText('Rem')
    expect(screen.getByText(/5 unowned/)).toBeInTheDocument()
  })

  it('sends an approval after confirmation', async () => {
    renderPage()
    await screen.findByText('Rem')
    await userEvent.click(screen.getAllByRole('button', { name: 'Approve' })[0])
    await userEvent.click(screen.getByRole('button', { name: 'Approve claim' }))
    await waitFor(() =>
      expect(api.decideModerationClaim).toHaveBeenCalledWith(10, { approve: true, reason: '' }),
    )
  })

  it('sends a rejection with the reason the mod typed', async () => {
    renderPage()
    await screen.findByText('Rem')
    await userEvent.click(screen.getAllByRole('button', { name: 'Reject' })[0])
    await userEvent.type(screen.getByLabelText(/reason/i), 'Not your account')
    await userEvent.click(screen.getByRole('button', { name: 'Reject claim' }))
    await waitFor(() =>
      expect(api.decideModerationClaim).toHaveBeenCalledWith(10, {
        approve: false,
        reason: 'Not your account',
      }),
    )
  })

  it('says so when there is nothing pending', async () => {
    api.listModerationClaims.mockResolvedValue({
      status: 'pending',
      counts: { pending: 0, approved: 0, rejected: 0 },
      items: [],
      total: 0,
    })
    renderPage()
    expect(await screen.findByText(/no pending claims/i)).toBeInTheDocument()
  })

  it('hides the bulk approve until a user filter is applied', async () => {
    renderPage()
    await screen.findByText('Rem')
    expect(screen.queryByRole('button', { name: /approve all/i })).not.toBeInTheDocument()

    await userEvent.type(screen.getByLabelText('User'), 'ref-ada')
    expect(await screen.findByRole('button', { name: /approve all 2/i })).toBeInTheDocument()
  })

  it('bulk approves every pending claim for the filtered user', async () => {
    renderPage()
    await screen.findByText('Rem')
    await userEvent.type(screen.getByLabelText('User'), 'ref-ada')
    await userEvent.click(await screen.findByRole('button', { name: /approve all/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Approve all' }))
    await waitFor(() => expect(api.approveAllModerationClaims).toHaveBeenCalledWith('ref-ada'))
  })

  it('reports what the cap left behind', async () => {
    api.approveAllModerationClaims.mockResolvedValue({
      success: true,
      approved_count: 25,
      images_granted: 40,
      remaining: 3,
    })
    renderPage()
    await screen.findByText('Rem')
    await userEvent.type(screen.getByLabelText('User'), 'ref-ada')
    await userEvent.click(await screen.findByRole('button', { name: /approve all/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Approve all' }))
    expect(await screen.findByText(/3 still pending/i)).toBeInTheDocument()
  })
})

/**
 * The report queue. The one thing it must get right is the split the tab offers:
 * images still live with reports, versus images the threshold already removed.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ listModerationReports: vi.fn() }))

vi.mock('../../api', () => ({
  getImageUrl: (p) => p || '',
  apiClient: api,
}))

vi.mock('../../config', () => ({ thumbUrl: (t) => `thumb:${t}` }))

import { renderWithQueryClient } from '../../test/renderWithQueryClient'
import ReportsPage from './ReportsPage'

const OPEN = {
  status: 'reported',
  counts: { reported: 1, removed: 1 },
  items: [
    {
      id: 1,
      character: 'Rem',
      url: 'https://cdn/a.png',
      thumb: 'thumbs/1.webp',
      state: 'active',
      removed_reason: null,
      removed_at: null,
      report_count: 1,
      last_report_at: '2026-01-02T00:00:00Z',
      reports: [{ reason: 'nsfw', at: '2026-01-02T00:00:00Z', reporter: 'Ada Otter' }],
    },
  ],
  total: 1,
}

const REMOVED = {
  status: 'removed',
  counts: { reported: 1, removed: 1 },
  items: [
    {
      id: 2,
      character: 'Emilia',
      url: 'https://cdn/b.png',
      thumb: 'thumbs/2.webp',
      state: 'removed',
      removed_reason: 'reported: nsfw',
      removed_at: '2026-01-03T00:00:00Z',
      report_count: 2,
      last_report_at: '2026-01-03T00:00:00Z',
      reports: [
        { reason: 'nsfw', at: '2026-01-03T00:00:00Z', reporter: 'Ada Otter' },
        { reason: 'wrong_character', at: '2026-01-03T01:00:00Z', reporter: null },
      ],
    },
  ],
  total: 1,
}

function renderPage() {
  return renderWithQueryClient(
    <MemoryRouter>
      <ReportsPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.listModerationReports
    .mockReset()
    .mockImplementation(({ status }) => Promise.resolve(status === 'removed' ? REMOVED : OPEN))
})

describe('ReportsPage', () => {
  it('shows still-live reports by default, with reason and reporter', async () => {
    renderPage()
    expect(await screen.findByText('Rem')).toBeInTheDocument()
    expect(screen.getByText('NSFW')).toBeInTheDocument()
    expect(screen.getByText(/Ada Otter/)).toBeInTheDocument()
    expect(api.listModerationReports).toHaveBeenCalledWith({ status: 'reported' })
  })

  it('switches to images the threshold removed', async () => {
    renderPage()
    await screen.findByText('Rem')
    await userEvent.click(screen.getByRole('radio', { name: /removed by reports/i }))
    await waitFor(() =>
      expect(api.listModerationReports).toHaveBeenCalledWith({ status: 'removed' }),
    )
    expect(await screen.findByText('Emilia')).toBeInTheDocument()
    expect(screen.getByText(/2 reports/)).toBeInTheDocument()
  })

  it('says so when a bucket is empty', async () => {
    api.listModerationReports.mockResolvedValue({
      status: 'reported',
      counts: { reported: 0, removed: 0 },
      items: [],
      total: 0,
    })
    renderPage()
    expect(await screen.findByText(/no open reports/i)).toBeInTheDocument()
  })
})

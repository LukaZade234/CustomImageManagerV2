/**
 * The duplicate audit. Its job is to make an existing duplicate findable and
 * give a moderator the one verb that fixes it — a soft remove — without turning
 * into a purge queue. The rest is list states.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  listModerationDuplicates: vi.fn(),
  purgeCustomImage: vi.fn(),
  restoreImages: vi.fn(),
}))

vi.mock('../../api', () => ({
  getImageUrl: (p) => p || '',
  apiClient: api,
}))

vi.mock('../../config', () => ({ thumbUrl: (t) => `thumb:${t}` }))

import { renderWithQueryClient } from '../../test/renderWithQueryClient'
import DuplicatesPage from './DuplicatesPage'

const CLUSTERS = {
  clusters: [
    {
      hash: 'abcdef0123456789',
      character: 'Rem',
      count: 2,
      images: [
        {
          id: 1,
          character: 'Rem',
          url: 'https://cdn/a.png',
          thumb: 'thumbs/1.webp',
          state: 'active',
          owner: 'Ada Otter',
          added_at: '2026-01-02T00:00:00Z',
        },
        {
          id: 2,
          character: 'Rem',
          url: 'https://cdn/b.png',
          thumb: 'thumbs/2.webp',
          state: 'removed',
          owner: null,
          added_at: '2026-01-03T00:00:00Z',
        },
      ],
    },
  ],
  total: 2,
}

function renderPage() {
  return renderWithQueryClient(
    <MemoryRouter>
      <DuplicatesPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.listModerationDuplicates.mockReset().mockResolvedValue(CLUSTERS)
  api.purgeCustomImage.mockReset().mockResolvedValue({})
  api.restoreImages.mockReset().mockResolvedValue({})
})

describe('DuplicatesPage', () => {
  it('shows a cluster and where each copy lives', async () => {
    renderPage()
    expect(await screen.findByText('2 copies')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Rem' })).toHaveAttribute('href', '/character/Rem')
    expect(screen.getByText(/Ada Otter/)).toBeInTheDocument()
  })

  it('opens the character page from a copy’s thumbnail', async () => {
    renderPage()
    const thumbs = await screen.findAllByRole('link', { name: /open rem/i })
    expect(thumbs).toHaveLength(2)
    expect(thumbs[0]).toHaveAttribute('href', '/character/Rem')
  })

  it('permanently deletes the active copy after a confirmation', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /^delete$/i }))
    expect(api.purgeCustomImage).not.toHaveBeenCalled()
    await userEvent.click(screen.getByRole('button', { name: /delete forever/i }))
    await waitFor(() =>
      expect(api.purgeCustomImage).toHaveBeenCalledWith('Rem', 'https://cdn/a.png'),
    )
  })

  it('restores a removed copy instead of removing it', async () => {
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /restore/i }))
    await waitFor(() =>
      expect(api.restoreImages).toHaveBeenCalledWith('Rem', ['https://cdn/b.png']),
    )
  })

  it('says so when there is nothing to review', async () => {
    api.listModerationDuplicates.mockResolvedValue({ clusters: [], total: 0 })
    renderPage()
    expect(await screen.findByText(/no duplicates/i)).toBeInTheDocument()
  })
})

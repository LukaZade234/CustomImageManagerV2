/**
 * The cut-over preview.
 *
 * Owner-only, and read-only: it renders what the cleanup script wrote and never
 * deletes. These tests pin the parts that would matter if they broke — the owner
 * gate, the "no preview yet" state being told apart from a failure, and the two
 * lists (what dies, what is recovered) actually being shown with their counts.
 */
import { screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getMe: vi.fn(),
  getModerationCutover: vi.fn(),
}))

vi.mock('../../api', () => ({
  getImageUrl: (p) => p || '',
  getPortraitUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: api,
}))

import RequireOwner from '../../components/RequireOwner'
import { renderWithQueryClient } from '../../test/renderWithQueryClient'
import CutoverPage from './CutoverPage'

const PREVIEW = {
  generated_at: '2026-09-16T12:00:00Z',
  account: 'tester',
  export: { unique_urls: 3, malformed: [], malformed_total: 0 },
  counts: {
    keepers: 5,
    delete_candidates: 1,
    recoverable: 1,
    foreign_urls: 1,
    multi_image_posts: 0,
  },
  delete: [
    {
      file_id: 'deadbeef',
      post_id: 'p1',
      image_count: 1,
      url: 'https://cdn.imgchest.com/files/deadbeef.png',
    },
  ],
  recover: [{ character: 'A2', url: 'https://cdn.imgchest.com/files/cafe.png' }],
  dead: [{ character: 'Albedo', url: 'https://cdn.imgchest.com/files/0812f6b02d38.png' }],
  foreign: [{ character: 'Someone Else', url: 'https://i.imgur.com/zzz.png' }],
  warnings: [],
  executed: false,
}

function renderCutover() {
  return renderWithQueryClient(
    <MemoryRouter initialEntries={['/moderation/cutover']}>
      <Routes>
        <Route path="/" element={<p>home</p>} />
        <Route
          path="/moderation/cutover"
          element={
            <RequireOwner>
              <CutoverPage />
            </RequireOwner>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.getMe.mockReset()
  api.getModerationCutover.mockReset()
  api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'owner', is_owner: true })
  api.getModerationCutover.mockResolvedValue({ available: true, preview: PREVIEW })
})

describe('the owner gate', () => {
  it('sends a non-owner home without rendering the page', async () => {
    api.getMe.mockResolvedValue({ handle: 'Moss', role: 'moderator', is_owner: false })
    renderCutover()
    expect(await screen.findByText('home')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { name: 'Cut-over' })).not.toBeInTheDocument()
  })

  it('shows the owner the preview', async () => {
    renderCutover()
    expect(await screen.findByRole('heading', { name: 'Cut-over' })).toBeInTheDocument()
  })
})

describe('the preview states', () => {
  it('says nothing has been generated rather than showing an empty run', async () => {
    api.getModerationCutover.mockResolvedValue({ available: false })
    renderCutover()
    expect(await screen.findByText(/no preview yet/i)).toBeInTheDocument()
  })

  it('surfaces a failed load as an error, not an empty preview', async () => {
    api.getModerationCutover.mockRejectedValue(new Error('The cleanup preview could not be read.'))
    renderCutover()
    expect(await screen.findByText(/could not load the preview/i)).toBeInTheDocument()
  })
})

describe('what the preview shows', () => {
  it('shows both lists, as images with identifiers under them', async () => {
    renderCutover()
    // The pictures, not just their ids: reviewing is a visual judgement.
    await screen.findByText('A2')
    const images = document.querySelectorAll('.cutover__grid img')
    expect([...images].map((img) => img.getAttribute('src'))).toEqual([
      'https://cdn.imgchest.com/files/deadbeef.png',
      'https://cdn.imgchest.com/files/cafe.png',
      'https://cdn.imgchest.com/files/0812f6b02d38.png',
    ])
    expect(screen.getByText('deadbeef')).toBeInTheDocument()
    expect(screen.getByText('A2')).toBeInTheDocument()
    expect(screen.getByText(/to delete permanently/i)).toBeInTheDocument()
    expect(screen.getByText(/recovered into Removed/i)).toBeInTheDocument()
  })

  it('lists dead files separately, and never among those recovered', async () => {
    // The export records what was pasted into Discord, not what is still
    // hosted. Recovering a 404 would add a broken image for staff to remove.
    renderCutover()
    await screen.findByText(/no longer hosted/i)
    expect(screen.getByText('Albedo')).toBeInTheDocument()
    // It is in its own section, not the recover grid.
    const recoverSection = screen.getByText(/recovered into Removed/i).closest('section')
    expect(recoverSection).not.toHaveTextContent('Albedo')
  })

  it('hides external URLs behind the filter, and shows them when asked', async () => {
    // The export is Discord's, so it carries other people's hosts. Recovering
    // one would put a foreign image on the site, so they are review-only.
    const { default: userEvent } = await import('@testing-library/user-event')
    renderCutover()
    await screen.findByText('A2')

    // Default view: app images only.
    expect(screen.queryByText('Someone Else')).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('radio', { name: 'External only' }))
    expect(screen.getByText('Someone Else')).toBeInTheDocument()
    // The delete list is this account's own posts, so it is not shown here.
    expect(screen.queryByText('deadbeef')).not.toBeInTheDocument()
  })

  it('never hides the irreversible list under the default filter', async () => {
    // "App images only" is the default, and the delete list must survive it —
    // it is the half that cannot be undone.
    renderCutover()
    expect(await screen.findByText('deadbeef')).toBeInTheDocument()
  })

  it('does not claim the run happened when it has not', async () => {
    renderCutover()
    expect(await screen.findByText(/it has not been run/i)).toBeInTheDocument()
  })

  it('reports the run once it has happened', async () => {
    api.getModerationCutover.mockResolvedValue({
      available: true,
      preview: { ...PREVIEW, executed: true, deleted: 1, recovered: 1 },
    })
    renderCutover()
    expect(await screen.findByText(/it has since been run/i)).toBeInTheDocument()
  })
})

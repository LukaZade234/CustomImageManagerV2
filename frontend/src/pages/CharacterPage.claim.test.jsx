/**
 * The claim banner as it appears on a character page.
 *
 * The page is what decides whether the banner exists at all, so this checks the
 * wiring the component test cannot: that `claimable`/`myClaim` from the gallery
 * response reach the banner, and that filing sends the character name.
 */
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { claimCharacter, served } = vi.hoisted(() => ({
  claimCharacter: vi.fn().mockResolvedValue({ status: 'filed', claim: { id: 1 } }),
  served: { rows: [], copiedIds: [], lastBatchIds: [], claimable: null, myClaim: null },
}))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  getPortraitUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: new Proxy(
    {
      getCustomImagesForChar: vi.fn(async () => ({
        rows: served.rows,
        copiedIds: served.copiedIds ?? [],
        lastBatchIds: served.lastBatchIds ?? [],
        claimable: served.claimable,
        myClaim: served.myClaim,
      })),
      findCatalogCharacter: vi.fn(async (name) => ({
        found: true,
        character: { name, series: 'Re:Zero', rank: '1', image: 'rem.png', in_library: true },
      })),
      claimCharacter,
      getMe: vi.fn(async () => ({
        handle: 'Amber Otter',
        role: 'user',
        signed_in: true,
        is_moderator: false,
      })),
    },
    {
      get: (target, prop) => (prop in target ? target[prop] : vi.fn().mockResolvedValue({})),
    },
  ),
}))

import { useStore } from '../store/useStore'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import CharacterPage from './CharacterPage'

function renderPage() {
  return renderWithQueryClient(
    <MemoryRouter initialEntries={['/character/Rem']}>
      <Routes>
        <Route path="/character/:name" element={<CharacterPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  claimCharacter.mockClear()
  served.rows = []
  served.claimable = null
  served.myClaim = null
  useStore.setState({
    characters: [{ name: 'Rem', series: 'Re:Zero', rank: '1', image: 'rem.png' }],
    savedCharacters: [],
    customImages: { Rem: [] },
    lastUpdated: {},
    loading: false,
    error: null,
    searchQuery: '',
    toasts: [],
    me: { handle: 'Amber Otter', role: 'user', is_moderator: false, signed_in: true },
  })
})

describe('claim banner on a character page', () => {
  it('appears with the counts when the character has unowned images', async () => {
    served.claimable = { active: 3, removed: 2 }
    renderPage()
    expect(await screen.findByText('Were these images yours?')).toBeInTheDocument()
    expect(screen.getByText(/3 in the gallery and 2 in the Removed drawer/)).toBeInTheDocument()
  })

  it('does not appear when there is nothing unowned', async () => {
    served.claimable = null
    renderPage()
    await screen.findByRole('button', { name: /^select$/i })
    expect(screen.queryByText('Were these images yours?')).not.toBeInTheDocument()
  })

  it('files a claim for this character after confirmation', async () => {
    served.claimable = { active: 1, removed: 0 }
    renderPage()
    await userEvent.click(await screen.findByRole('button', { name: /claim this image/i }))
    await userEvent.click(screen.getByRole('button', { name: 'Send request' }))
    await waitFor(() => expect(claimCharacter).toHaveBeenCalledWith('Rem'))
  })

  it('shows the awaiting-review state for a pending claim', async () => {
    served.claimable = { active: 1, removed: 0 }
    served.myClaim = { status: 'pending' }
    renderPage()
    expect(await screen.findByText(/awaiting review/i)).toBeInTheDocument()
  })
})

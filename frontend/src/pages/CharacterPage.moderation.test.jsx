/**
 * The ownership split on the character page.
 *
 * The rule this protects: your own images offer Remove, everyone else's offer
 * Hide, and a mixed selection has to show both counts rather than silently
 * doing one of them. DECISIONS.md section 1.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const ROWS = [
  { id: 1, url: 'https://cdn/mine.png', owner: 'Amber Otter', is_mine: true, hidden: false },
  { id: 2, url: 'https://cdn/theirs.png', owner: 'Jade Lynx', is_mine: false, hidden: false },
  { id: 3, url: 'https://cdn/hidden.png', owner: 'Jade Lynx', is_mine: false, hidden: true },
]

// vi.mock is hoisted above the module body, so the spies it closes over have to
// be created in a hoisted block too.
const { hideImages, deleteCustomImages, served } = vi.hoisted(() => ({
  hideImages: vi.fn().mockResolvedValue({ hidden: 1 }),
  deleteCustomImages: vi.fn().mockResolvedValue({ removed: ['https://cdn/mine.png'] }),
  // The page refetches on mount, so seeding the store alone is not enough --
  // whatever this serves is what ends up on screen.
  served: { rows: [] },
}))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: new Proxy(
    {
      getCustomImagesForChar: vi.fn(async () => served.rows),
      hideImages,
      deleteCustomImages,
    },
    {
      get: (target, prop) => (prop in target ? target[prop] : vi.fn().mockResolvedValue({})),
    },
  ),
}))

import { useStore } from '../store/useStore'
import CharacterPage from './CharacterPage'

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/character/Rem']}>
      <Routes>
        <Route path="/character/:name" element={<CharacterPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  hideImages.mockClear()
  deleteCustomImages.mockClear()
  served.rows = ROWS
  useStore.setState({
    characters: [{ name: 'Rem', series: 'Re:Zero', rank: '1', image: 'rem.png' }],
    savedCharacters: [],
    characterImages: { Rem: ROWS },
    customImages: { Rem: ROWS.map((r) => r.url) },
    lastUpdated: {},
    loading: false,
    error: null,
    searchQuery: '',
    toasts: [],
    me: { handle: 'Amber Otter', role: 'user', is_moderator: false },
  })
})

async function enterRemoveMode(user) {
  await user.click(await screen.findByRole('button', { name: /remove or hide/i }))
}

describe('ownership split', () => {
  it('hides hidden images until you ask for them', async () => {
    renderPage()
    expect(await screen.findByTitle('Added by you')).toBeInTheDocument()
    // Two of the three rows are visible; the hidden one is not among them.
    expect(screen.getAllByTitle(/^Added by/)).toHaveLength(2)
    expect(screen.queryByText('Hidden')).not.toBeInTheDocument()
  })

  it('offers to show the hidden ones, with a count', async () => {
    renderPage()
    expect(await screen.findByRole('button', { name: /show 1 hidden/i })).toBeInTheDocument()
  })

  it('reveals hidden images when asked, marked as hidden', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /show 1 hidden/i }))
    expect(screen.getAllByTitle(/^Added by/)).toHaveLength(3)
    expect(screen.getByText('Hidden')).toBeInTheDocument()
  })

  it('starts with both actions disabled and at zero', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterRemoveMode(user)
    expect(screen.getByRole('button', { name: /remove mine \(0\)/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /hide theirs \(0\)/i })).toBeDisabled()
  })

  it('counts a mixed selection under both actions', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterRemoveMode(user)
    await user.click(screen.getByTitle('Added by you'))
    await user.click(screen.getByTitle('Added by Jade Lynx'))
    expect(screen.getByRole('button', { name: /remove mine \(1\)/i })).toBeEnabled()
    expect(screen.getByRole('button', { name: /hide theirs \(1\)/i })).toBeEnabled()
  })

  it('will not let you remove an image that is not yours', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterRemoveMode(user)
    await user.click(screen.getByTitle('Added by Jade Lynx'))
    expect(screen.getByRole('button', { name: /remove mine \(0\)/i })).toBeDisabled()
    expect(screen.getByRole('button', { name: /hide theirs \(1\)/i })).toBeEnabled()
  })

  it('hides someone else’s image rather than deleting it', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterRemoveMode(user)
    await user.click(screen.getByTitle('Added by Jade Lynx'))
    await user.click(screen.getByRole('button', { name: /hide theirs \(1\)/i }))
    expect(hideImages).toHaveBeenCalledWith([2])
    expect(deleteCustomImages).not.toHaveBeenCalled()
  })

  it('asks for confirmation before removing your own', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterRemoveMode(user)
    await user.click(screen.getByTitle('Added by you'))
    await user.click(screen.getByRole('button', { name: /remove mine \(1\)/i }))

    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/remove 1 image\?/i)).toBeInTheDocument()
    // Nothing has happened yet — the confirmation is a real gate.
    expect(deleteCustomImages).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: /^remove$/i }))
    await waitFor(() =>
      expect(deleteCustomImages).toHaveBeenCalledWith('Rem', ['https://cdn/mine.png']),
    )
  })

  it('cancelling the confirmation removes nothing', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterRemoveMode(user)
    await user.click(screen.getByTitle('Added by you'))
    await user.click(screen.getByRole('button', { name: /remove mine \(1\)/i }))
    // Scoped to the dialog: the toolbar has a Cancel of its own.
    const dialog = await screen.findByRole('dialog')
    await user.click(within(dialog).getByRole('button', { name: /cancel/i }))
    expect(deleteCustomImages).not.toHaveBeenCalled()
  })
})

describe('attribution', () => {
  it('labels each image with who added it', async () => {
    renderPage()
    expect(await screen.findByTitle('Added by you')).toBeInTheDocument()
    expect(screen.getByTitle('Added by Jade Lynx')).toBeInTheDocument()
  })

  it('says so plainly when an image predates ownership tracking', async () => {
    served.rows = [
      { id: 9, url: 'https://cdn/legacy.png', owner: null, is_mine: false, hidden: false },
    ]
    renderPage()
    expect(await screen.findByTitle('Added before ownership was tracked')).toBeInTheDocument()
  })
})

/**
 * The ownership split on the character page.
 *
 * The rule this protects: your own images offer Remove, everyone else's offer
 * Hide, and a mixed selection has to show both counts rather than silently
 * doing one of them. DECISIONS.md section 1.
 */
import { screen, waitFor, within } from '@testing-library/react'
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
  // whatever this serves is what ends up on screen. An object rather than a bare
  // array so the copy-history fields can be exercised.
  served: { rows: [], copiedIds: [], lastBatchIds: [] },
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
      })),
      // The page fetches its own record now instead of reading a downloaded roster.
      findCatalogCharacter: vi.fn(async (name) => ({
        found: true,
        character: { name, series: 'Re:Zero', rank: '1', image: 'rem.png', in_library: true },
      })),
      hideImages,
      deleteCustomImages,
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
  hideImages.mockClear()
  deleteCustomImages.mockClear()
  served.rows = ROWS
  served.copiedIds = []
  served.lastBatchIds = []
  useStore.setState({
    characters: [{ name: 'Rem', series: 'Re:Zero', rank: '1', image: 'rem.png' }],
    savedCharacters: [],
    customImages: { Rem: ROWS.map((r) => r.url) },
    lastUpdated: {},
    loading: false,
    error: null,
    searchQuery: '',
    toasts: [],
    me: { handle: 'Amber Otter', role: 'user', is_moderator: false },
  })
})

async function enterSelectMode(user) {
  await user.click(await screen.findByRole('button', { name: /^select$/i }))
}

const removeButton = () => screen.queryByRole('button', { name: /^remove \(\d+\)$/i })
const hideButton = () => screen.queryByRole('button', { name: /^hide \(\d+\)$/i })

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

  it('offers no verb at all until something is selected', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterSelectMode(user)

    // The old toolbar showed "Remove mine (0)" and "Hide theirs (0)", both
    // disabled: a dead end you could enter, read and leave without either ever
    // becoming usable. A verb that cannot act is now absent, not greyed out.
    expect(removeButton()).not.toBeInTheDocument()
    expect(hideButton()).not.toBeInTheDocument()
    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '0 of 2 selected',
    )
  })

  it('counts a mixed selection under both actions', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterSelectMode(user)
    await user.click(screen.getByTitle('Added by you'))
    await user.click(screen.getByTitle('Added by Jade Lynx'))
    expect(removeButton()).toHaveAccessibleName('Remove (1)')
    expect(hideButton()).toHaveAccessibleName('Hide (1)')
    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '2 of 2 selected',
    )
  })

  it('will not let you remove an image that is not yours', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterSelectMode(user)
    await user.click(screen.getByTitle('Added by Jade Lynx'))
    expect(removeButton()).not.toBeInTheDocument()
    expect(hideButton()).toHaveAccessibleName('Hide (1)')
  })

  it('reaches your own images without reading every thumbnail', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterSelectMode(user)
    await user.click(screen.getByRole('button', { name: /select mine \(1\)/i }))

    // Exactly the one image you added, and so exactly the verb that fits it.
    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '1 of 2 selected',
    )
    expect(removeButton()).toHaveAccessibleName('Remove (1)')
    expect(hideButton()).not.toBeInTheDocument()
  })

  it('hides someone else’s image rather than deleting it', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterSelectMode(user)
    await user.click(screen.getByTitle('Added by Jade Lynx'))
    await user.click(screen.getByRole('button', { name: /^hide \(1\)$/i }))
    expect(hideImages).toHaveBeenCalledWith([2])
    expect(deleteCustomImages).not.toHaveBeenCalled()
  })

  it('asks for confirmation before removing your own', async () => {
    const user = userEvent.setup()
    renderPage()
    await enterSelectMode(user)
    await user.click(screen.getByTitle('Added by you'))
    await user.click(screen.getByRole('button', { name: /^remove \(1\)$/i }))

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
    await enterSelectMode(user)
    await user.click(screen.getByTitle('Added by you'))
    await user.click(screen.getByRole('button', { name: /^remove \(1\)$/i }))
    // Scoped to the dialog, which is the only Cancel on the page.
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

describe('the $ai door', () => {
  /**
   * The header button used to copy a command for every image the instant it was
   * clicked. It then preselected everything, which decided the very thing you
   * came to pick — and on a gallery past Mudae's cap it preselected a set the
   * bot would reject. It now opens an empty selection.
   */
  it('opens the selection with nothing chosen', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^\$ai command$/i }))

    const bar = screen.getByRole('region', { name: /selection actions/i })
    expect(bar).toHaveTextContent('0 of 2 selected')
    expect(
      within(bar).queryByRole('button', { name: /Copy \$ai command/i }),
    ).not.toBeInTheDocument()
  })

  it('lets you build the selection yourself before copying', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^\$ai command$/i }))
    await user.click(screen.getByTitle('Added by Jade Lynx'))

    const bar = screen.getByRole('region', { name: /selection actions/i })
    expect(bar).toHaveTextContent('1 of 2 selected')
    expect(within(bar).getByRole('button', { name: /Copy \$ai command/i })).toBeInTheDocument()
  })

  it('says nothing about $ai in a gallery that has no images', async () => {
    served.rows = []
    renderPage()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /^\$ai command$/i })).toBeDisabled(),
    )
  })

  it('caps select-all at the Mudae limit of 100 images', async () => {
    // A command over 100 images is rejected by Mudae, so "select all" in this
    // door has to stop at 100 rather than put an invalid command one click away.
    const user = userEvent.setup()
    served.rows = Array.from({ length: 256 }, (_, i) => ({
      id: i + 1,
      url: `https://cdn/${i}.png`,
      owner: null,
      is_mine: false,
      hidden: false,
    }))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^\$ai command$/i }))
    await user.click(screen.getByRole('button', { name: 'Select first 100' }))

    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '100 of 256 selected',
    )
  })

  it('does not cap the plain Select door, which no Mudae limit applies to', async () => {
    const user = userEvent.setup()
    served.rows = Array.from({ length: 256 }, (_, i) => ({
      id: i + 1,
      url: `https://cdn/${i}.png`,
      owner: null,
      is_mine: false,
      hidden: false,
    }))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^Select$/i }))
    await user.click(screen.getByRole('button', { name: 'Select all (256)' }))

    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '256 of 256 selected',
    )
  })

  it('refuses the 101st click in the $ai door rather than truncating later', async () => {
    const user = userEvent.setup()
    served.rows = Array.from({ length: 101 }, (_, i) => ({
      id: i + 1,
      url: `https://cdn/${i}.png`,
      owner: null,
      is_mine: false,
      hidden: false,
    }))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^\$ai command$/i }))
    // The label already reflects the cap, so the block is visible before the click.
    expect(screen.getByRole('button', { name: 'Select first 100' })).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Select first 100' }))
    // After select-first-100 the only unselected image is the 101st (the last
    // in the gallery). Clicking it must be refused, not accepted.
    const tiles = screen.getAllByTitle('Added before ownership was tracked')
    expect(tiles).toHaveLength(101)
    await user.click(tiles[100])

    // 101 images, so select-all takes 100 and the 101st is refused.
    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '100 of 101 selected',
    )
    // Toasts live in the store; the Toast component is not mounted here.
    expect(useStore.getState().toasts.map((t) => t.msg)).toContainEqual(
      expect.stringMatching(/Mudae allows 100 images per \$ai command/i),
    )
  })

  it('refuses to copy a plain-Select selection over the limit, with a reason', async () => {
    // The plain door may select everything (remove/hide/download are uncapped),
    // but the command is still Mudae's to refuse. It must refuse here too, and
    // never quietly copy a shorter command than was selected.
    const user = userEvent.setup()
    served.rows = Array.from({ length: 150 }, (_, i) => ({
      id: i + 1,
      url: `https://cdn/${i}.png`,
      owner: null,
      is_mine: false,
      hidden: false,
    }))
    renderPage()
    await user.click(await screen.findByRole('button', { name: /^Select$/i }))
    await user.click(screen.getByRole('button', { name: 'Select all (150)' }))
    await user.click(screen.getByRole('button', { name: 'Copy $ai command' }))

    // Nothing was copied, and the dialog never opened.
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(useStore.getState().toasts.map((t) => t.msg)).toEqual([
      expect.stringMatching(/Mudae allows 100 images per \$ai command/i),
    ])
  })

  it('offers the copy-history helpers only in the $ai door', async () => {
    const user = userEvent.setup()
    served.copiedIds = [1, 2]
    served.lastBatchIds = [2]
    renderPage()

    // Plain Select: the helpers are not part of ordinary selection.
    await user.click(await screen.findByRole('button', { name: /^Select$/i }))
    expect(screen.queryByRole('button', { name: /Select copied/i })).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Done$/i }))

    // $ai: they are, and each selects its own set.
    await user.click(screen.getByRole('button', { name: /^\$ai command$/i }))
    await user.click(screen.getByRole('button', { name: 'Select last batch (1)' }))
    expect(screen.getByRole('region', { name: /selection actions/i })).toHaveTextContent(
      '1 of 2 selected',
    )
  })
})

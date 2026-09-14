/**
 * Renders every route with a populated store.
 *
 * This exists because the build does not type-check: a component referencing an
 * identifier it never imported compiles cleanly and only fails at runtime, on
 * the page, in front of a user. A render is the cheapest thing that catches it,
 * and it also guards the migration onto the shared primitives.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

// A memoizing proxy so the same vi.fn is returned for a given method across
// calls, which lets a test stub the one it cares about while every other call
// resolves to `{}`. Without the cache each access made a fresh mock and stubs
// could never be asserted on.
const api = vi.hoisted(() => {
  const cache = new Map()
  const apiClient = new Proxy(
    {},
    {
      get: (_target, prop) => {
        if (!cache.has(prop)) cache.set(prop, vi.fn().mockResolvedValue({}))
        return cache.get(prop)
      },
    },
  )
  return { apiClient }
})

vi.mock('../api', () => ({
  getImageUrl: (p) => (p ? `/images/${p}` : ''),
  apiUrl: (p) => p,
  apiClient: api.apiClient,
}))

import { useStore } from '../store/useStore'
import AddPage from './AddPage'
import CharacterPage from './CharacterPage'
import CustomsPage from './CustomsPage'
import HomePage from './HomePage'
import SavedTab from './profile/SavedTab'
import SearchResultsPage from './SearchResultsPage'

const CHARACTERS = [
  { name: 'Ayanami Rei', series: 'Neon Genesis Evangelion', rank: 12, image: 'rei.png' },
  { name: 'Makise Kurisu', series: 'Steins;Gate', rank: 4, image: 'kurisu.png' },
]

beforeEach(() => {
  api.apiClient.searchCharacters.mockReset()
  api.apiClient.searchCharacters.mockResolvedValue({ items: [], total: 0 })
  useStore.setState({
    characters: CHARACTERS,
    savedCharacters: [{ name: 'Ayanami Rei' }],
    customImages: { 'Ayanami Rei': ['https://cdn.example/a.png'] },
    lastUpdated: {},
    currentCharacter: null,
    loading: false,
    error: null,
    searchQuery: '',
    toasts: [],
  })
})

function renderAt(ui, route = '/') {
  return render(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>)
}

describe('page smoke tests', () => {
  it('renders the home page with its counts', () => {
    renderAt(<HomePage />)
    expect(screen.getByRole('heading', { level: 1, name: /imgmanager/i })).toBeInTheDocument()
  })

  it('renders the saved list with a saved character', () => {
    // Saved moved out of its own page and into a profile tab, so it is a
    // section heading now rather than the page title.
    renderAt(<SavedTab />)
    expect(screen.getByRole('heading', { level: 2, name: /saved characters/i })).toBeInTheDocument()
    expect(screen.getByText('Ayanami Rei')).toBeInTheDocument()
  })

  it('shows an empty state when nothing is saved', () => {
    useStore.setState({ savedCharacters: [] })
    renderAt(<SavedTab />)
    expect(screen.getByText(/no saved characters yet/i)).toBeInTheDocument()
  })

  it('renders the customs page', () => {
    renderAt(<CustomsPage />)
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  it('renders the add page', () => {
    renderAt(<AddPage />)
    expect(screen.getByRole('heading', { level: 1 })).toBeInTheDocument()
  })

  it('renders server search results from the URL', async () => {
    api.apiClient.searchCharacters.mockImplementation(({ q, by }) => {
      const needle = q.toLowerCase()
      const items = CHARACTERS.filter((c) =>
        (by === 'series' ? c.series : c.name).toLowerCase().includes(needle),
      ).map((c) => ({ ...c, in_library: true }))
      return Promise.resolve({ items, total: items.length })
    })
    renderAt(<SearchResultsPage />, '/search?q=rei&by=name')
    expect(await screen.findByText('Ayanami Rei')).toBeInTheDocument()
    expect(screen.queryByText('Makise Kurisu')).not.toBeInTheDocument()
  })

  it('searches series when the URL says so', async () => {
    api.apiClient.searchCharacters.mockImplementation(({ q, by }) => {
      const needle = q.toLowerCase()
      const items = CHARACTERS.filter((c) =>
        (by === 'series' ? c.series : c.name).toLowerCase().includes(needle),
      ).map((c) => ({ ...c, in_library: true }))
      return Promise.resolve({ items, total: items.length })
    })
    renderAt(<SearchResultsPage />, '/search?q=steins&by=series')
    expect(await screen.findByText('Makise Kurisu')).toBeInTheDocument()
    expect(screen.queryByText('Ayanami Rei')).not.toBeInTheDocument()
  })

  it('asks the server for the chosen sort and order', async () => {
    useStore.setState({ searchSort: 'alphabet', searchOrder: 'asc' })
    renderAt(<SearchResultsPage />, '/search?q=a&by=name')
    await waitFor(() =>
      expect(api.apiClient.searchCharacters).toHaveBeenCalledWith(
        expect.objectContaining({ q: 'a', by: 'name', sort: 'alphabet', order: 'asc', page: 1 }),
      ),
    )
  })

  it('pages the results behind a Show more button', async () => {
    const many = Array.from({ length: 75 }, (_, i) => ({
      name: `Char ${String(i).padStart(2, '0')}`,
      series: 'S',
      rank: i + 1,
      image: `${i}.png`,
      in_library: true,
    }))
    api.apiClient.searchCharacters.mockImplementation(({ page, perPage }) => {
      const start = (page - 1) * perPage
      return Promise.resolve({ items: many.slice(start, start + perPage), total: many.length })
    })
    renderAt(<SearchResultsPage />, '/search?q=char&by=name')
    await waitFor(() => expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(60))
    await userEvent.click(screen.getByRole('button', { name: /show 15 more/i }))
    await waitFor(() => expect(screen.getAllByRole('heading', { level: 3 })).toHaveLength(75))
  })

  it('sends a catalog-only result to the Add form', async () => {
    api.apiClient.searchCharacters.mockResolvedValue({
      items: [
        { name: 'Saber', series: 'Fate/stay night', rank: '4', image: '', in_library: false },
      ],
      total: 1,
    })
    renderAt(<SearchResultsPage />, '/search?q=saber&by=name')
    const link = await screen.findByRole('link', { name: /Saber/ })
    expect(link).toHaveAttribute('href', '/add?name=Saber')
  })

  it('renders a character page', () => {
    renderAt(<CharacterPage />, '/character/Ayanami%20Rei')
  })
})

describe('character page loading states', () => {
  /**
   * The page used to show "Character not found" whenever its record was absent,
   * and the record is absent for as long as the library takes to load. Every
   * refresh, bookmark and link pasted into Discord therefore opened on an error
   * claiming the character did not exist.
   */
  it('shows a skeleton while the library is still loading, not an error', () => {
    useStore.setState({ characters: [], loading: true })
    renderAt(<CharacterPage />, '/character/Ayanami%20Rei')

    expect(screen.getByText(/Loading character/i)).toBeInTheDocument()
    expect(screen.queryByText(/not found/i)).not.toBeInTheDocument()
    // The real page leads with the portrait; the skeleton must not put the
    // identity in the narrow first column and the portrait beside it.
    const top = document.querySelector('.character-top-section')
    expect(top.firstElementChild).toHaveClass('char-image-section')
    expect(document.querySelectorAll('.gallery-item-wrapper--skeleton').length).toBeGreaterThan(0)
  })

  it('only says not-found once the library has actually arrived', () => {
    useStore.setState({ characters: CHARACTERS, loading: false })
    renderAt(<CharacterPage />, '/character/Nobody%20At%20All')

    expect(
      screen.getByRole('heading', { level: 1, name: /Character not found/i }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Nothing here called/i)).toBeInTheDocument()
  })

  it('offers a way back rather than stranding you', () => {
    useStore.setState({ characters: CHARACTERS, loading: false })
    renderAt(<CharacterPage />, '/character/Nobody%20At%20All')
    expect(screen.getByRole('link', { name: /Back to search/i })).toHaveAttribute('href', '/')
  })
})

describe('an empty gallery', () => {
  /**
   * An empty gallery was a blank strip under the drop hint, which reads as a
   * load that failed rather than a character nobody has added an image to. The
   * hidden case is worse: hiding the last image emptied the gallery with no
   * sign that the images still exist.
   */
  /** The other tests here render the page bare; these need the :name param. */
  function renderCharacter() {
    return render(
      <MemoryRouter initialEntries={['/character/Ayanami%20Rei']}>
        <Routes>
          <Route path="/character/:name" element={<CharacterPage />} />
        </Routes>
      </MemoryRouter>,
    )
  }

  it('says there is nothing here yet, and offers the way to add one', () => {
    useStore.setState({ characterImages: { 'Ayanami Rei': [] } })
    renderCharacter()

    expect(screen.getByText(/No custom images yet/i)).toBeInTheDocument()
    // Its own button, inside the gallery, rather than only the toolbar's — the
    // point is that the way out sits where the missing images would be.
    const gallery = within(document.querySelector('.custom-images-gallery'))
    expect(gallery.getByRole('button', { name: /^Add image$/i })).toBeInTheDocument()
  })

  it('distinguishes an empty gallery from one you have hidden all of', () => {
    useStore.setState({
      characterImages: {
        'Ayanami Rei': [{ id: 1, url: 'https://cdn.example/a.png', hidden: true, is_mine: false }],
      },
    })
    renderCharacter()

    expect(screen.getByText(/The only image here is one you hid/i)).toBeInTheDocument()
    expect(screen.queryByText(/No custom images yet/i)).not.toBeInTheDocument()
  })
})

describe('profile lists', () => {
  /**
   * Characters are all the same 9:14, so a list of them is a grid of equal
   * cards. Under justified rows a short last row stretched to fill the width,
   * which on a phone meant two normal cards and then one enormous one.
   */
  it('lays saved characters out as a uniform grid', () => {
    renderAt(<SavedTab />)
    const grid = document.querySelector('.profile-grid')
    expect(grid).toHaveClass('profile-grid--uniform')
    // Fillers exist to level a justified row; a grid has no row to level.
    expect(document.querySelectorAll('.profile-grid__filler').length).toBe(0)
  })
})

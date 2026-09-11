/**
 * Renders every route with a populated store.
 *
 * This exists because the build does not type-check: a component referencing an
 * identifier it never imported compiles cleanly and only fails at runtime, on
 * the page, in front of a user. A render is the cheapest thing that catches it,
 * and it also guards the migration onto the shared primitives.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  getImageUrl: (p) => (p ? `/images/${p}` : ''),
  apiUrl: (p) => p,
  apiClient: new Proxy({}, { get: () => vi.fn().mockResolvedValue({}) }),
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

  it('renders search results from the URL, not from store state', () => {
    renderAt(<SearchResultsPage />, '/search?q=rei&by=name')
    expect(screen.getByRole('heading', { level: 1, name: /search results/i })).toBeInTheDocument()
    expect(screen.getByText('Ayanami Rei')).toBeInTheDocument()
    expect(screen.queryByText('Makise Kurisu')).not.toBeInTheDocument()
  })

  it('searches series when the URL says so', () => {
    renderAt(<SearchResultsPage />, '/search?q=steins&by=series')
    expect(screen.getByText('Makise Kurisu')).toBeInTheDocument()
    expect(screen.queryByText('Ayanami Rei')).not.toBeInTheDocument()
  })

  it('renders a character page', () => {
    renderAt(<CharacterPage />, '/character/Ayanami%20Rei')
  })
})

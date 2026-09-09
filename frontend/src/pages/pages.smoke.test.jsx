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

import AddPage from './AddPage'
import CharacterPage from './CharacterPage'
import CustomsPage from './CustomsPage'
import HomePage from './HomePage'
import SavedPage from './SavedPage'
import SearchResultsPage from './SearchResultsPage'
import { useStore } from '../store/useStore'

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
    expect(screen.getByRole('heading', { level: 1, name: /welcome/i })).toBeInTheDocument()
  })

  it('renders the saved page with a saved character', () => {
    renderAt(<SavedPage />)
    expect(screen.getByRole('heading', { level: 1, name: /saved characters/i })).toBeInTheDocument()
    expect(screen.getByText('Ayanami Rei')).toBeInTheDocument()
  })

  it('shows an empty state when nothing is saved', () => {
    useStore.setState({ savedCharacters: [] })
    renderAt(<SavedPage />)
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

  it('renders search results for a query', () => {
    useStore.setState({ searchQuery: 'rei' })
    renderAt(<SearchResultsPage />)
    expect(screen.getByRole('heading', { level: 1, name: /search results/i })).toBeInTheDocument()
  })

  it('renders a character page', () => {
    renderAt(<CharacterPage />, '/character/Ayanami%20Rei')
  })
})

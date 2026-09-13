/**
 * The profile lists' filter row.
 *
 * It is the navbar's bar, so what matters here is that the search is the shared
 * `.search-field` inside the shared `.filter-bar`, and that the filter is the
 * one arrow menu at every width: the current choice stated beside it when there
 * is room, the arrow alone when there is not. The one-line layout itself is CSS,
 * which jsdom cannot see.
 */
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import ListControls from './ListControls'

const OPTIONS = [
  { value: 'recent', label: 'Recently saved' },
  { value: 'character', label: 'Character (A–Z)' },
]

/** A MediaQueryList stand-in that answers `matches` directly. */
const mql = (matches) => ({
  matches,
  media: '',
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  addListener: () => {},
  removeListener: () => {},
  dispatchEvent: () => false,
})

const wide = () => vi.fn().mockImplementation(() => mql(false))
const narrow = () => vi.fn().mockImplementation(() => mql(true))

function setup(overrides = {}) {
  const props = {
    label: 'Search by character',
    query: '',
    onQuery: vi.fn(),
    sort: 'recent',
    onSort: vi.fn(),
    order: 'asc',
    onOrder: vi.fn(),
    options: OPTIONS,
    shown: 3,
    total: 3,
    ...overrides,
  }
  render(<ListControls {...props} />)
  return props
}

describe('ListControls', () => {
  it('searches through the shared bar', () => {
    window.matchMedia = wide()
    setup()
    expect(document.querySelector('.filter-bar .search-field')).toBeInTheDocument()
    expect(screen.getByRole('searchbox', { name: /search by character/i })).toBeInTheDocument()
  })

  it('states the current filter beside the arrow when there is room', () => {
    window.matchMedia = wide()
    setup()
    expect(screen.getByText('Recently saved asc.')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })

  it('folds to the arrow alone, and opens the sort options, when there is not', async () => {
    window.matchMedia = narrow()
    try {
      const props = setup()
      expect(screen.queryByText('Recently saved asc.')).not.toBeInTheDocument()
      const toggle = screen.getByRole('button', { name: /filter/i })
      expect(toggle).toHaveAttribute('aria-expanded', 'false')

      await userEvent.click(toggle)
      expect(toggle).toHaveAttribute('aria-expanded', 'true')
      const menu = screen.getByRole('menu', { name: /filter/i })
      await userEvent.click(within(menu).getByRole('menuitemradio', { name: /character/i }))
      expect(props.onSort).toHaveBeenCalledWith('character')
    } finally {
      window.matchMedia = wide()
    }
  })
})

/**
 * The landing page.
 *
 * Everything on it comes from the library, and every section hides itself when
 * it has nothing to show — so the tests that matter are the empty ones. A page
 * that renders "Top contributors" above a list of one name, or an empty "Just
 * added" strip, looks worse than a page that simply omits them.
 */
import { screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ getStats: vi.fn() }))

vi.mock('../api', () => ({ getImageUrl: (p) => p || '', apiClient: api }))
vi.mock('../config', () => ({ apiUrl: (p) => p }))

import { renderWithQueryClient } from '../test/renderWithQueryClient'
import HomePage from './HomePage'

const FULL = {
  custom_images: 8552,
  characters_with_customs: 707,
  series_count: 441,
  recent: [{ id: 9, url: 'https://cdn/x.png', thumb: '/thumbs/9.webp', character: 'Reze' }],
  best_covered: [
    { name: 'Columbina', series: 'Genshin Impact', images: 256, image: 'c.png' },
    { name: 'Lucy', series: 'Cyberpunk: Edgerunners', images: 117, image: '' },
  ],
  top_series: [
    {
      series: 'Genshin Impact',
      images: 808,
      characters: 31,
      top_character: 'Columbina',
      top_character_images: 256,
      top_character_image: 'c.png',
    },
  ],
  most_viewed: [{ name: 'Sandrone', series: 'Genshin Impact', viewers: 14, image: 's.png' }],
  contributors: [
    { handle: 'Someone', images: 40 },
    { handle: 'Another', images: 12 },
  ],
}

const show = (stats) =>
  renderWithQueryClient(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
    { queries: [[['stats'], stats]] },
  )

beforeEach(() => {
  api.getStats.mockReset()
})

describe('HomePage', () => {
  it('shows the three totals, grouped with their labels', () => {
    show(FULL)
    expect(screen.getByText('8,552')).toBeInTheDocument()
    expect(screen.getByText('707')).toBeInTheDocument()
    expect(screen.getByText('441')).toBeInTheDocument()
    expect(screen.getByText('Custom images')).toBeInTheDocument()
  })

  it('links each highlight somewhere useful', () => {
    show(FULL)
    expect(screen.getByRole('link', { name: /Reze/ })).toHaveAttribute('href', '/character/Reze')
    // Columbina is both a most-popular character and Genshin's most
    // represented character; the character cards link to her page, while the
    // ledger row she names stays a link into the series.
    const columbina = screen.getAllByRole('link', { name: /Columbina/ })
    for (const link of columbina.filter((l) => l.getAttribute('href')?.startsWith('/character/'))) {
      expect(link).toHaveAttribute('href', '/character/Columbina')
    }
    expect(columbina.some((l) => l.getAttribute('href')?.startsWith('/search?'))).toBe(true)
    // The series card, not the "Genshin Impact" subtitle on Columbina's row.
    expect(screen.getByRole('link', { name: /808 images/ })).toHaveAttribute(
      'href',
      '/search?q=Genshin%20Impact&by=series',
    )
  })

  it('names the character carrying each series and how many images that is', () => {
    show(FULL)
    expect(document.querySelector('.home-series-ledger__leadname')).toHaveTextContent('Columbina')
    expect(document.querySelector('.home-series-ledger__leadcount')).toHaveTextContent('256')
  })

  it('prefers the thumbnail but falls back to the original', () => {
    show(FULL)
    // alt="" is deliberate -- the picture is decoration next to the name it
    // sits under -- so these are presentational and have no img role to query.
    expect(document.querySelector('.home-recent__thumb')).toHaveAttribute('src', '/thumbs/9.webp')
  })

  it('falls back to the original when an image has no thumbnail', () => {
    show({ ...FULL, recent: [{ id: 9, url: 'https://cdn/x.png', thumb: null, character: 'Reze' }] })
    expect(document.querySelector('.home-recent__thumb')).toHaveAttribute(
      'src',
      'https://cdn/x.png',
    )
  })

  it('says who the contributor ranking counts', () => {
    show(FULL)
    expect(screen.getByText(/Anonymous uploads are not ranked/i)).toBeInTheDocument()
  })

  it('shows the caller their own standing when it is below the ranked few', () => {
    show({ ...FULL, you: { rank: 57, handle: 'Me', images: 3 } })
    expect(screen.getByText(/#57/)).toBeInTheDocument()
    expect(screen.getByText(/3 images/)).toBeInTheDocument()
  })

  it('does not repeat the standing when the caller is already on the board', () => {
    show({ ...FULL, you: { rank: 2, handle: 'Another', images: 12 } })
    expect(screen.queryByText(/You are/)).not.toBeInTheDocument()
  })

  it('shows no standing line for a visitor who is not ranked', () => {
    show(FULL)
    expect(screen.queryByText(/You are/)).not.toBeInTheDocument()
  })

  it('hides the contributor ranking when there is only one name', () => {
    show({ ...FULL, contributors: [{ handle: 'Someone', images: 40 }] })
    expect(screen.queryByText(/Top contributors/i)).not.toBeInTheDocument()
  })

  it('explains that the visit ranking counts people, not visits', () => {
    show(FULL)
    expect(screen.getByText(/different people looked/i)).toBeInTheDocument()
  })

  it('hides most-visited until the view log has something in it', () => {
    show({ ...FULL, most_viewed: [] })
    expect(screen.queryByText(/Most visited this week/i)).not.toBeInTheDocument()
  })

  it('hides every section that has nothing in it', () => {
    show({ custom_images: 0, characters_with_customs: 0, series_count: 0 })
    // These must be the headings the page actually renders: a name that no
    // longer exists would make every assertion here pass for nothing.
    for (const heading of [
      /Just added/i,
      /Most visited this week/i,
      /Most popular characters/i,
      /Most popular series/i,
      /Top contributors/i,
    ])
      expect(screen.queryByText(heading)).not.toBeInTheDocument()

    // The totals still render, so the page is never blank.
    expect(screen.getByRole('heading', { level: 1, name: /imgmanager/i })).toBeInTheDocument()
    expect(screen.getAllByText('0')).toHaveLength(3)
  })

  it('survives a response with no highlight keys at all', () => {
    show({ custom_images: 5, characters_with_customs: 2 })
    expect(screen.getByText('5')).toBeInTheDocument()
  })

  it('shows a home-shaped skeleton while the library loads', () => {
    // A request that never resolves stands in for the fetch being in flight.
    api.getStats.mockReturnValue(new Promise(() => {}))
    renderWithQueryClient(
      <MemoryRouter>
        <HomePage />
      </MemoryRouter>,
    )
    expect(document.querySelector('.skeleton-hero')).toBeInTheDocument()
    // More than the hero: the page must not collapse to one card and then jump.
    expect(document.querySelectorAll('.page-loading-shell').length).toBeGreaterThan(1)
    expect(screen.getByText(/Loading the library/i)).toBeInTheDocument()
    // The old copy claimed it was fetching "your collection", which Home never
    // does.
    expect(screen.queryByText(/your collection/i)).not.toBeInTheDocument()
  })

  it('no longer explains the site to people already using it', () => {
    show(FULL)
    expect(screen.queryByText(/Key Features/i)).not.toBeInTheDocument()
  })
})

/**
 * The landing page.
 *
 * Everything on it comes from the library, and every section hides itself when
 * it has nothing to show — so the tests that matter are the empty ones. A page
 * that renders "Top contributors" above a list of one name, or an empty "Just
 * added" strip, looks worse than a page that simply omits them.
 */
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ getImageUrl: (p) => p || '', apiClient: {} }))
vi.mock('../config', () => ({ apiUrl: (p) => p }))

import { useStore } from '../store/useStore'
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
  top_series: [{ series: 'Genshin Impact', images: 808, characters: 31 }],
  contributors: [
    { handle: 'Someone', images: 40 },
    { handle: 'Another', images: 12 },
  ],
}

const show = (stats) => {
  useStore.setState({ stats, loading: false, error: null, loadStats: vi.fn() })
  render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  useStore.setState({ stats: null, loading: false, error: null })
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
    expect(screen.getByRole('link', { name: /Columbina/ })).toHaveAttribute(
      'href',
      '/character/Columbina',
    )
    // The series card, not the "Genshin Impact" subtitle on Columbina's row.
    expect(screen.getByRole('link', { name: /808 images/ })).toHaveAttribute(
      'href',
      '/search?q=Genshin%20Impact&by=series',
    )
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

  it('hides the contributor ranking when there is only one name', () => {
    show({ ...FULL, contributors: [{ handle: 'Someone', images: 40 }] })
    expect(screen.queryByText(/Top contributors/i)).not.toBeInTheDocument()
  })

  it('hides every section that has nothing in it', () => {
    show({ custom_images: 0, characters_with_customs: 0, series_count: 0 })
    for (const heading of [
      /Just added/i,
      /Best covered/i,
      /Browse by series/i,
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

  it('no longer explains the site to people already using it', () => {
    show(FULL)
    expect(screen.queryByText(/Key Features/i)).not.toBeInTheDocument()
  })
})

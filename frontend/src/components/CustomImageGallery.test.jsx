/**
 * The gallery grid.
 *
 * Each image used to carry two overlapping mouse-only handlers — one on the
 * wrapper for selecting, one on the <img> for opening — so neither action was
 * reachable from a keyboard. They are now one real button whose meaning depends
 * on the gallery's mode, which is what these tests pin.
 */
import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ getImageUrl: (p) => p || '', apiUrl: (p) => p }))

import CustomImageGallery from './CustomImageGallery'

const ROWS = [
  { id: 1, url: 'https://cdn/a.png', thumb: '/thumbs/1.webp', is_mine: true, owner: null },
  { id: 2, url: 'https://cdn/b.png', thumb: '/thumbs/2.webp', is_mine: false, owner: 'Someone' },
]

const NO_MODES = { select: false, reorder: false }

function setup(overrides = {}) {
  const props = {
    rows: ROWS,
    ratios: {},
    modes: NO_MODES,
    selectedUrls: [],
    reorder: {
      isDragging: false,
      dropTargetIndex: null,
      dragIndices: null,
      itemProps: () => ({}),
      consumeClickAfterDrag: () => false,
    },
    onToggleSelect: vi.fn(),
    onOpenImage: vi.fn(),
    onImageLoad: vi.fn(),
    onDragOver: vi.fn(),
    ...overrides,
  }
  render(<CustomImageGallery {...props} />)
  return props
}

describe('CustomImageGallery', () => {
  it('exposes each image as a button the keyboard can reach', () => {
    setup()
    const buttons = screen.getAllByRole('button')
    expect(buttons).toHaveLength(2)
    expect(buttons[0]).toHaveAccessibleName(/Open image 1, added by you/i)
    expect(buttons[1]).toHaveAccessibleName(/Open image 2, added by someone/i)
  })

  it('opens the image when browsing', async () => {
    const props = setup()
    await userEvent.click(screen.getAllByRole('button')[1])
    expect(props.onOpenImage).toHaveBeenCalledWith(1)
    expect(props.onToggleSelect).not.toHaveBeenCalled()
  })

  it('opens from the keyboard too', async () => {
    const props = setup()
    screen.getAllByRole('button')[0].focus()
    await userEvent.keyboard('{Enter}')
    expect(props.onOpenImage).toHaveBeenCalledWith(0)
  })

  it('selects instead of opening once a mode is active', async () => {
    const props = setup({ modes: { ...NO_MODES, select: true } })
    const button = screen.getAllByRole('button')[0]
    expect(button).toHaveAccessibleName(/Select image 1/i)

    await userEvent.click(button)
    expect(props.onToggleSelect).toHaveBeenCalledWith('https://cdn/a.png')
    expect(props.onOpenImage).not.toHaveBeenCalled()
  })

  it('reports selection state to assistive technology', () => {
    setup({ modes: { ...NO_MODES, select: true }, selectedUrls: ['https://cdn/a.png'] })
    const [first, second] = screen.getAllByRole('button')
    expect(first).toHaveAttribute('aria-pressed', 'true')
    expect(second).toHaveAttribute('aria-pressed', 'false')
  })

  it('says who added an image once you have picked it, and not before', () => {
    // Ownership decides which verb the toolbar offers, so it belongs on what
    // you picked. Tagging all 256 thumbnails throughout the mode, as remove
    // mode used to, put the answer everywhere except where it was needed.
    setup({ modes: { ...NO_MODES, select: true } })
    expect(screen.queryByText('Yours')).not.toBeInTheDocument()

    cleanup()
    setup({ modes: { ...NO_MODES, select: true }, selectedUrls: ['https://cdn/a.png'] })
    expect(screen.getByText('Yours')).toBeInTheDocument()
    // The other image is not selected, so nothing is said about it.
    expect(screen.queryByText('Someone')).not.toBeInTheDocument()
  })

  it('is not a toggle when there is nothing to select', () => {
    setup()
    expect(screen.getAllByRole('button')[0]).not.toHaveAttribute('aria-pressed')
  })

  it('swallows the click that ends a drag', async () => {
    const props = setup({
      modes: { ...NO_MODES, reorder: true },
      reorder: {
        isDragging: false,
        dropTargetIndex: null,
        dragIndices: null,
        itemProps: () => ({}),
        consumeClickAfterDrag: () => true,
      },
    })
    await userEvent.click(screen.getAllByRole('button')[0])
    expect(props.onToggleSelect).not.toHaveBeenCalled()
    expect(props.onOpenImage).not.toHaveBeenCalled()
  })

  it('samples a pixel instead of opening while picking the accent', async () => {
    const onPick = vi.fn()
    setup({ pick: true, onPick })
    const first = screen.getAllByRole('button')[0]
    expect(first).toHaveAccessibleName(/Pick the accent colour from image 1/i)
    await userEvent.click(first)
    expect(onPick).toHaveBeenCalledTimes(1)
    // jsdom has no layout, so the point collapses to the origin; what matters
    // here is that the row (with its id) reaches the handler at all.
    expect(onPick.mock.calls[0][0]).toBe(ROWS[0])
    expect(onPick.mock.calls[0][1]).toEqual({ u: 0, v: 0 })
  })
})

describe('layout', () => {
  const mql = (matches) => ({
    matches,
    media: '',
    addEventListener: () => {},
    removeEventListener: () => {},
  })

  it('lays out in justified rows on a wide viewport', () => {
    setup()
    const gallery = document.querySelector('.custom-images-gallery')
    expect(gallery).not.toHaveClass('is-masonry')
    // The fillers level the last row, which only rows have.
    expect(document.querySelectorAll('.gallery-filler').length).toBeGreaterThan(0)
  })

  it('lays out in uniform columns on a narrow one', () => {
    // One portrait across a 390px screen is a gallery you scroll past one image
    // at a time. Columns of equal width and unequal height fit four or five.
    window.matchMedia = vi.fn().mockImplementation(() => mql(true))
    try {
      setup()
      expect(document.querySelector('.custom-images-gallery')).toHaveClass('is-masonry')
      expect(document.querySelectorAll('.gallery-filler').length).toBe(0)
    } finally {
      window.matchMedia = vi.fn().mockImplementation(() => mql(false))
    }
  })
})

describe('loading', () => {
  /**
   * The bug this guards: while a character's images were still in flight the
   * gallery fell through to its empty state and announced "No custom images
   * yet" for a gallery that simply had not answered.
   */
  it('shows frames rather than the empty state while images load', () => {
    setup({ rows: [], loading: true, empty: <p>No custom images yet</p> })
    expect(document.querySelectorAll('.gallery-item-wrapper--skeleton')).toHaveLength(8)
    expect(screen.queryByText('No custom images yet')).not.toBeInTheDocument()
  })

  it('falls back to the empty state once the fetch has settled empty', () => {
    setup({ rows: [], loading: false, empty: <p>No custom images yet</p> })
    expect(screen.getByText('No custom images yet')).toBeInTheDocument()
  })
})

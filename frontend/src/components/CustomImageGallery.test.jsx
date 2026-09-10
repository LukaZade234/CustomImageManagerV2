/**
 * The gallery grid.
 *
 * Each image used to carry two overlapping mouse-only handlers — one on the
 * wrapper for selecting, one on the <img> for opening — so neither action was
 * reachable from a keyboard. They are now one real button whose meaning depends
 * on the gallery's mode, which is what these tests pin.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({ getImageUrl: (p) => p || '', apiUrl: (p) => p }))

import CustomImageGallery from './CustomImageGallery'

const ROWS = [
  { id: 1, url: 'https://cdn/a.png', thumb: '/thumbs/1.webp', is_mine: true, owner: null },
  { id: 2, url: 'https://cdn/b.png', thumb: '/thumbs/2.webp', is_mine: false, owner: 'Someone' },
]

const NO_MODES = { ai: false, remove: false, download: false, reorder: false }

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
    const props = setup({ modes: { ...NO_MODES, remove: true } })
    const button = screen.getAllByRole('button')[0]
    expect(button).toHaveAccessibleName(/Select image 1/i)

    await userEvent.click(button)
    expect(props.onToggleSelect).toHaveBeenCalledWith('https://cdn/a.png')
    expect(props.onOpenImage).not.toHaveBeenCalled()
  })

  it('reports selection state to assistive technology', () => {
    setup({ modes: { ...NO_MODES, remove: true }, selectedUrls: ['https://cdn/a.png'] })
    const [first, second] = screen.getAllByRole('button')
    expect(first).toHaveAttribute('aria-pressed', 'true')
    expect(second).toHaveAttribute('aria-pressed', 'false')
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
})

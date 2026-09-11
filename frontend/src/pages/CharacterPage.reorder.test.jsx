/**
 * What a reorder session costs.
 *
 * Every drop used to POST the order, refetch the whole character, and raise a
 * success toast, so rearranging a dozen images meant a dozen round trips and a
 * stack of a dozen identical toasts over the gallery being rearranged. These
 * tests pin the replacement: the order is applied locally, saved once per move
 * with the requests chained, confirmed once at the end, and reverted only when
 * something actually moved.
 *
 * They drive the session through the keyboard rather than a pointer drag —
 * jsdom has no layout, so `elementFromPoint` cannot resolve a drop target, but
 * the arrow keys run the same `applyReorder` path.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const reorderCustomImages = vi.fn()
const getCustomImagesForChar = vi.fn()

vi.mock('../api', () => ({
  getImageUrl: (p) => (p ? `/images/${p}` : ''),
  apiUrl: (p) => p,
  apiClient: new Proxy(
    {},
    {
      get: (_target, prop) => {
        if (prop === 'reorderCustomImages') return reorderCustomImages
        if (prop === 'getCustomImagesForChar') return getCustomImagesForChar
        return vi.fn().mockResolvedValue({})
      },
    },
  ),
}))

import { useStore } from '../store/useStore'
import CharacterPage from './CharacterPage'

const ROWS = ['a', 'b', 'c'].map((id, i) => ({
  id: i + 1,
  url: `https://cdn.example/${id}.png`,
  is_mine: true,
  hidden: false,
  uploader_label: 'you',
}))

beforeEach(() => {
  reorderCustomImages.mockReset().mockResolvedValue({})
  getCustomImagesForChar.mockReset().mockResolvedValue(ROWS)
  useStore.setState({
    characters: [{ name: 'Rei', series: 'Evangelion', rank: 1, image: 'rei.png' }],
    savedCharacters: [],
    characterImages: { Rei: ROWS },
    loading: false,
    toasts: [],
  })
})

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/character/Rei']}>
      <Routes>
        <Route path="/character/:name" element={<CharacterPage />} />
      </Routes>
    </MemoryRouter>,
  )
}

/** Open reorder mode and move the first image one place to the right, `times` times. */
async function moveFirstImage(user, times) {
  await user.click(screen.getByRole('button', { name: /^Reorder$/i }))
  for (let i = 0; i < times; i++) {
    const slot = document.querySelector(`[data-reorder-slot="${i}"]`)
    slot.focus()
    await user.keyboard('{ArrowRight}')
  }
}

const toastMessages = () => useStore.getState().toasts.map((t) => t.msg)

describe('a reorder session', () => {
  it('saves each move without a toast or a refetch, then confirms once on Done', async () => {
    const user = userEvent.setup()
    renderPage()
    const initialFetches = getCustomImagesForChar.mock.calls.length

    await moveFirstImage(user, 2)

    await waitFor(() => expect(reorderCustomImages).toHaveBeenCalledTimes(2))
    expect(getCustomImagesForChar.mock.calls.length).toBe(initialFetches)
    expect(toastMessages()).toEqual([])

    // The gallery has to show the new order even though nothing was refetched:
    // the first image walked to the end.
    expect(useStore.getState().characterImages.Rei.map((r) => r.id)).toEqual([2, 3, 1])

    await user.click(screen.getByRole('button', { name: /^Done$/i }))
    await waitFor(() => expect(toastMessages()).toEqual(['New order saved']))
  })

  it('sends the moves in order rather than racing them', async () => {
    const user = userEvent.setup()
    const settle = []
    reorderCustomImages.mockImplementation(
      () => new Promise((resolve) => settle.push(() => resolve({}))),
    )
    renderPage()

    await moveFirstImage(user, 2)

    // The second request must not have been issued while the first is open.
    expect(reorderCustomImages).toHaveBeenCalledTimes(1)
    settle[0]()
    await waitFor(() => expect(reorderCustomImages).toHaveBeenCalledTimes(2))
  })

  it('says so once when a save fails, and shows what the server actually holds', async () => {
    const user = userEvent.setup()
    reorderCustomImages.mockRejectedValue(new Error('Order rejected'))
    renderPage()
    const initialFetches = getCustomImagesForChar.mock.calls.length

    await moveFirstImage(user, 2)

    await waitFor(() => expect(toastMessages()).toEqual(['Order rejected']))
    expect(getCustomImagesForChar.mock.calls.length).toBeGreaterThan(initialFetches)

    // And Done does not then claim the order was saved.
    await user.click(screen.getByRole('button', { name: /^Done$/i }))
    await waitFor(() => expect(toastMessages()).toEqual(['Order rejected']))
  })

  it('leaves quietly when Discard is pressed without having moved anything', async () => {
    const user = userEvent.setup()
    renderPage()

    await user.click(screen.getByRole('button', { name: /^Reorder$/i }))
    await user.click(screen.getByRole('button', { name: /^Discard changes$/i }))

    // No confirmation to answer, no write, no toast: there is nothing to undo.
    expect(screen.queryByText(/discard the new order/i)).not.toBeInTheDocument()
    expect(reorderCustomImages).not.toHaveBeenCalled()
    expect(toastMessages()).toEqual([])
    expect(screen.getByRole('button', { name: /^Reorder$/i })).toBeInTheDocument()
  })

  it('asks before discarding real moves, and restores the order it opened on', async () => {
    const user = userEvent.setup()
    renderPage()

    await moveFirstImage(user, 1)
    await waitFor(() => expect(reorderCustomImages).toHaveBeenCalledTimes(1))

    await user.click(screen.getByRole('button', { name: /^Discard changes$/i }))
    expect(screen.getByText(/discard the new order/i)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: /^Discard$/i }))

    await waitFor(() => expect(reorderCustomImages).toHaveBeenCalledTimes(2))
    expect(reorderCustomImages.mock.calls[1][1]).toEqual(ROWS.map((r) => r.url))
    await waitFor(() =>
      expect(toastMessages()).toEqual(['Order reverted to before you started reordering.']),
    )
  })
})

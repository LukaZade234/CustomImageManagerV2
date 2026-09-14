/**
 * The customs list is served page by page.
 *
 * What matters is that search, sort and paging reach the *server* — if any of
 * them quietly fell back to filtering in the browser, the page would still look
 * right while downloading the whole library again, which is the regression this
 * change exists to prevent.
 */
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listCustoms } = vi.hoisted(() => ({ listCustoms: vi.fn() }))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  getPortraitUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: { listCustoms },
}))

import { useStore } from '../store/useStore'
import CustomsPage from './CustomsPage'

const page = (items, overrides = {}) => ({
  items,
  page: 1,
  per_page: 20,
  total: items.length,
  total_pages: 1,
  ...overrides,
})

const ITEM = {
  name: 'Rem',
  series: 'Re:Zero',
  rank: '1',
  image: 'rem.png',
  count: 5,
  previews: [
    { id: 1, url: 'https://cdn/a.png', thumb: '/thumbs/1.webp' },
    { id: 2, url: 'https://cdn/b.png', thumb: '/thumbs/2.webp' },
  ],
}

const lastCall = () => listCustoms.mock.calls.at(-1)[0]

beforeEach(() => {
  // The filters are remembered across visits now, so each test starts from the
  // documented defaults rather than whatever the one before it chose.
  localStorage.clear()
  useStore.setState({ searchMode: 'name', customsSort: 'recent', customsOrder: 'desc' })
  listCustoms.mockReset()
  listCustoms.mockResolvedValue(page([ITEM]))
})

const renderPage = () =>
  render(
    <MemoryRouter>
      <CustomsPage />
    </MemoryRouter>,
  )

/** The current URL, plus a real "back" the way the browser would offer. */
function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <span data-testid="location">{location.pathname + location.search}</span>
      <button type="button" onClick={() => navigate(-1)}>
        back
      </button>
    </>
  )
}

const renderRouted = (entries = ['/customs']) =>
  render(
    <MemoryRouter initialEntries={entries}>
      <CustomsPage />
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )

describe('server-driven listing', () => {
  it('renders what the server returned', async () => {
    renderPage()
    expect(await screen.findByText('Rem')).toBeInTheDocument()
    expect(screen.getByText('5 images')).toBeInTheDocument()
    expect(screen.getByText(/1 characters with custom images/)).toBeInTheDocument()
  })

  it('shows the previews the server chose, as thumbnails', async () => {
    renderPage()
    await screen.findByText('Rem')
    const previews = document.querySelectorAll('.customs-preview-thumb')
    expect(previews).toHaveLength(2)
    // The row draws the WebP, never the 1.9 MB ImgChest original.
    expect(previews[0]).toHaveAttribute('src', '/thumbs/1.webp')
    expect(previews[0]).toHaveAttribute('loading', 'lazy')
  })

  it('sends the search term to the server rather than filtering locally', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    await user.type(screen.getByRole('searchbox'), 'emilia')
    await waitFor(() => expect(lastCall().q).toBe('emilia'))
  })

  it('debounces typing into one request', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    const before = listCustoms.mock.calls.length
    await user.type(screen.getByRole('searchbox'), 'emilia')
    await waitFor(() => expect(lastCall().q).toBe('emilia'))
    // Six keystrokes must not mean six round trips.
    expect(listCustoms.mock.calls.length - before).toBeLessThan(6)
  })

  it('sends the search mode', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    await user.click(screen.getByRole('button', { name: /Filter/i }))
    await user.click(
      within(screen.getByRole('group', { name: 'Search by' })).getByRole('menuitemradio', {
        name: 'Series',
      }),
    )
    await waitFor(() => expect(lastCall().by).toBe('series'))
  })

  it('sends the sort key and direction the server understands', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    await user.click(screen.getByRole('button', { name: /Filter/i }))
    await user.click(
      within(screen.getByRole('group', { name: 'Sort by' })).getByRole('menuitemradio', {
        name: 'Image count',
      }),
    )
    // Image count opens descending, which is the server's count_desc fragment.
    await waitFor(() => expect(lastCall().sort).toBe('count_desc'))
  })

  it('asks the server for the next page', async () => {
    const user = userEvent.setup()
    listCustoms.mockResolvedValue(page([ITEM], { total: 60, total_pages: 3 }))
    renderPage()
    await screen.findByText('Rem')
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(lastCall().page).toBe(2))
  })

  it('returns to the top of the new page', async () => {
    const user = userEvent.setup()
    const scrollTo = vi.spyOn(window, 'scrollTo').mockImplementation(() => {})
    listCustoms.mockResolvedValue(page([ITEM], { total: 60, total_pages: 3 }))
    renderPage()
    await screen.findByText('Rem')
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(lastCall().page).toBe(2))
    expect(scrollTo).toHaveBeenCalledWith(0, 0)
    scrollTo.mockRestore()
  })

  it('puts the page in the URL, so back steps through pages instead of leaving', async () => {
    const user = userEvent.setup()
    listCustoms.mockResolvedValue(page([ITEM], { total: 60, total_pages: 3 }))
    renderRouted()
    await screen.findByText('Rem')
    const location = () => screen.getByTestId('location').textContent
    expect(location()).toBe('/customs')

    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(location()).toBe('/customs?page=2'))
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(location()).toBe('/customs?page=3'))

    // The browser back is the previous page of results, not the route before
    // Browse Customs.
    await user.click(screen.getByRole('button', { name: 'back' }))
    await waitFor(() => expect(location()).toBe('/customs?page=2'))
    await waitFor(() => expect(lastCall().page).toBe(2))
  })

  it('makes a typed search a history entry, so back clears the filter', async () => {
    const user = userEvent.setup()
    renderRouted()
    await screen.findByText('Rem')
    const location = () => screen.getByTestId('location').textContent

    await user.type(screen.getByRole('searchbox'), 'rem')
    await waitFor(() => expect(lastCall().q).toBe('rem'))
    expect(location()).toBe('/customs?q=rem')

    await user.click(screen.getByRole('button', { name: 'back' }))
    await waitFor(() => expect(location()).toBe('/customs'))
    await waitFor(() => expect(lastCall().q).toBe(''))
  })

  it('restores a deep-linked page instead of clamping it to one', async () => {
    // Arriving at /customs?page=2 remounts the page with no result yet, so
    // total_pages is a placeholder 1. Clamping against that placeholder used to
    // rewrite the URL to page one before the page-2 fetch landed, which is what
    // made Back from a character page land on the first page.
    listCustoms.mockResolvedValue(page([ITEM], { total: 60, total_pages: 3 }))
    renderRouted(['/customs?page=2'])
    await screen.findByText('Rem')
    await waitFor(() => expect(lastCall().page).toBe(2))
    expect(screen.getByTestId('location').textContent).toBe('/customs?page=2')
    expect(listCustoms.mock.calls.some(([args]) => args.page === 1)).toBe(false)
  })

  it('reads rank as top-first in both directions', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    await user.click(screen.getByRole('button', { name: /Filter/i }))
    await user.click(
      within(screen.getByRole('group', { name: 'Sort by' })).getByRole('menuitemradio', {
        name: 'Rank',
      }),
    )
    // Rank opens descending: highest rank (lowest number) first.
    await waitFor(() => expect(lastCall().sort).toBe('rank_asc'))

    // Choosing a sort closes the panel, so reopen it for the direction.
    await user.click(screen.getByRole('button', { name: /Filter/i }))
    await user.click(
      within(screen.getByRole('group', { name: 'Order' })).getByRole('menuitemradio', {
        name: 'Ascending',
      }),
    )
    // Ascending means the lowest-ranked characters lead.
    await waitFor(() => expect(lastCall().sort).toBe('rank_desc'))
  })

  it('goes back to page one when the search changes', async () => {
    const user = userEvent.setup()
    listCustoms.mockResolvedValue(page([ITEM], { total: 60, total_pages: 3 }))
    renderPage()
    await screen.findByText('Rem')
    await user.click(screen.getByRole('button', { name: /next page/i }))
    await waitFor(() => expect(lastCall().page).toBe(2))
    await user.type(screen.getByRole('searchbox'), 'x')
    await waitFor(() => expect(lastCall().page).toBe(1))
  })
})

describe('states', () => {
  it('distinguishes an empty library from an empty search', async () => {
    listCustoms.mockResolvedValue(page([], { total: 0 }))
    renderPage()
    expect(await screen.findByText(/no custom images yet/i)).toBeInTheDocument()
  })

  it('says nothing matched when a search comes back empty', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    listCustoms.mockResolvedValue(page([], { total: 0 }))
    await user.type(screen.getByRole('searchbox'), 'zzzz')
    expect(await screen.findByText(/no matches/i)).toBeInTheDocument()
  })

  it('surfaces a failure instead of looking empty', async () => {
    listCustoms.mockRejectedValue(new Error('Gateway timeout'))
    renderPage()
    expect(await screen.findByText(/could not load the list/i)).toBeInTheDocument()
    expect(screen.getByText('Gateway timeout')).toBeInTheDocument()
  })
})

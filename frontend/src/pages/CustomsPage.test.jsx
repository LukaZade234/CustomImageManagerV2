/**
 * The customs list is served page by page.
 *
 * What matters is that search, sort and paging reach the *server* — if any of
 * them quietly fell back to filtering in the browser, the page would still look
 * right while downloading the whole library again, which is the regression this
 * change exists to prevent.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { listCustoms } = vi.hoisted(() => ({ listCustoms: vi.fn() }))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: { listCustoms },
}))

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
  previews: ['a.png', 'b.png'],
}

const lastCall = () => listCustoms.mock.calls.at(-1)[0]

beforeEach(() => {
  listCustoms.mockReset()
  listCustoms.mockResolvedValue(page([ITEM]))
})

const renderPage = () =>
  render(
    <MemoryRouter>
      <CustomsPage />
    </MemoryRouter>,
  )

describe('server-driven listing', () => {
  it('renders what the server returned', async () => {
    renderPage()
    expect(await screen.findByText('Rem')).toBeInTheDocument()
    expect(screen.getByText('5 images')).toBeInTheDocument()
    expect(screen.getByText(/1 characters with custom images/)).toBeInTheDocument()
  })

  it('shows the previews the server chose', async () => {
    renderPage()
    await screen.findByText('Rem')
    const previews = document.querySelectorAll('.customs-preview-thumb')
    expect(previews).toHaveLength(2)
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
    await user.click(screen.getByRole('radio', { name: 'Series' }))
    await waitFor(() => expect(lastCall().by).toBe('series'))
  })

  it('sends the sort key', async () => {
    const user = userEvent.setup()
    renderPage()
    await screen.findByText('Rem')
    await user.selectOptions(screen.getByLabelText(/sort by/i), 'count_desc')
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

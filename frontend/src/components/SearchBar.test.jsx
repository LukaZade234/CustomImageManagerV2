import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { useStore } from '../store/useStore'
import SearchBar from './SearchBar'

function LocationProbe() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <span data-testid="location">{`${location.pathname}${location.search}`}</span>
      <button type="button" onClick={() => navigate(-1)}>
        back
      </button>
    </>
  )
}

function renderBar(route = '/') {
  return render(
    <MemoryRouter initialEntries={[route]}>
      <SearchBar />
      <Routes>
        <Route path="*" element={<LocationProbe />} />
      </Routes>
    </MemoryRouter>,
  )
}

const currentLocation = () => screen.getByTestId('location').textContent
const filterButton = () => screen.getByRole('button', { name: /Filter/i })
const group = (name) => within(screen.getByRole('group', { name }))

beforeEach(() => {
  useStore.setState({ searchQuery: '', searchMode: 'name', searchSort: 'rank', searchOrder: 'asc' })
})

describe('SearchBar', () => {
  it('puts the query in the URL so results are linkable', async () => {
    const user = userEvent.setup()
    renderBar()
    await user.type(screen.getByRole('searchbox'), 'rei')
    expect(currentLocation()).toBe('/search?q=rei&by=name')
  })

  it('makes the search one history entry, so back returns to the page it started from', async () => {
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/customs']}>
        <SearchBar />
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )
    await user.type(screen.getByRole('searchbox'), 'rei')
    expect(currentLocation()).toBe('/search?q=rei&by=name')
    await user.click(screen.getByRole('button', { name: 'back' }))
    expect(currentLocation()).toBe('/customs')
  })

  it('adopts a query already present in the URL', async () => {
    const user = userEvent.setup()
    renderBar('/search?q=kurisu&by=series')
    expect(screen.getByRole('searchbox')).toHaveValue('kurisu')
    await user.click(filterButton())
    expect(group('Search by').getByRole('menuitemradio', { name: 'Series' })).toHaveAttribute(
      'aria-checked',
      'true',
    )
  })

  it('leaves the results route when the field is emptied', async () => {
    const user = userEvent.setup()
    renderBar('/search?q=rei&by=name')
    await user.clear(screen.getByRole('searchbox'))
    expect(currentLocation()).toBe('/')
  })

  it('returns to the page the search started from when the field is emptied', async () => {
    // Clearing used to force the home page, so a search begun on any other page
    // could only be abandoned by landing somewhere the reader never chose.
    const user = userEvent.setup()
    render(
      <MemoryRouter initialEntries={['/customs', '/search?q=rei&by=name']}>
        <SearchBar />
        <Routes>
          <Route path="*" element={<LocationProbe />} />
        </Routes>
      </MemoryRouter>,
    )
    await user.clear(screen.getByRole('searchbox'))
    expect(currentLocation()).toBe('/customs')
  })

  it('carries the mode into the URL when it is switched', async () => {
    const user = userEvent.setup()
    renderBar('/search?q=rei&by=name')
    await user.click(filterButton())
    await user.click(group('Search by').getByRole('menuitemradio', { name: 'Series' }))
    expect(currentLocation()).toBe('/search?q=rei&by=series')
  })

  it('does not navigate on a mode switch with an empty field', async () => {
    const user = userEvent.setup()
    renderBar('/saved')
    await user.click(filterButton())
    await user.click(group('Search by').getByRole('menuitemradio', { name: 'Series' }))
    expect(currentLocation()).toBe('/saved')
  })

  it('remembers the sort direction', async () => {
    const user = userEvent.setup()
    renderBar()
    await user.click(filterButton())
    await user.click(group('Order').getByRole('menuitemradio', { name: 'Descending' }))
    expect(useStore.getState().searchOrder).toBe('desc')
  })
})

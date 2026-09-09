import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it } from 'vitest'
import { useStore } from '../store/useStore'
import SearchBar from './SearchBar'

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>
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

beforeEach(() => {
  useStore.setState({ searchQuery: '', searchMode: 'name', searchSort: 'rank' })
})

describe('SearchBar', () => {
  it('puts the query in the URL so results are linkable', async () => {
    const user = userEvent.setup()
    renderBar()
    await user.type(screen.getByRole('searchbox'), 'rei')
    expect(currentLocation()).toBe('/search?q=rei&by=name')
  })

  it('adopts a query already present in the URL', () => {
    renderBar('/search?q=kurisu&by=series')
    expect(screen.getByRole('searchbox')).toHaveValue('kurisu')
    expect(screen.getByRole('radio', { name: 'Series' })).toBeChecked()
  })

  it('leaves the results route when the field is emptied', async () => {
    const user = userEvent.setup()
    renderBar('/search?q=rei&by=name')
    await user.clear(screen.getByRole('searchbox'))
    expect(currentLocation()).toBe('/')
  })

  it('carries the mode into the URL when it is switched', async () => {
    const user = userEvent.setup()
    renderBar('/search?q=rei&by=name')
    await user.click(screen.getByRole('radio', { name: 'Series' }))
    expect(currentLocation()).toBe('/search?q=rei&by=series')
  })

  it('does not navigate on a mode switch with an empty field', async () => {
    const user = userEvent.setup()
    renderBar('/saved')
    await user.click(screen.getByRole('radio', { name: 'Series' }))
    expect(currentLocation()).toBe('/saved')
  })
})

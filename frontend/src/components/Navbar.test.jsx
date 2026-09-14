/**
 * The navbar's identity control.
 *
 * Sign-in is an upgrade, never a wall, so what is worth pinning is that the app
 * is fully usable with no account and that the pseudonym is always visible.
 *
 * Signing in and out now live on the profile page — settings needed a home the
 * moment there was more than one of them — so the navbar's job is reduced to
 * naming you and offering the way there. ProfilePage.test.jsx covers the rest.
 */
import { screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { logout } = vi.hoisted(() => ({ logout: vi.fn().mockResolvedValue({}) }))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: new Proxy(
    { logout },
    { get: (t, k) => (k in t ? t[k] : vi.fn().mockResolvedValue({})) },
  ),
}))

import { useStore } from '../store/useStore'
import { renderWithQueryClient } from '../test/renderWithQueryClient'
import Navbar from './Navbar'

// The navbar reads `me` from react-query now; the tests still describe it by
// seeding the store, so hand that value to the query cache at render time.
const renderNav = (route = '/') =>
  renderWithQueryClient(
    <MemoryRouter initialEntries={[route]}>
      <Navbar />
    </MemoryRouter>,
    { queries: [[['me'], useStore.getState().me]] },
  )

beforeEach(() => {
  logout.mockClear()
  useStore.setState({
    theme: 'system',
    searchQuery: '',
    searchMode: 'name',
    searchSort: 'rank',
    searchOrder: 'asc',
  })
})

describe('signed out', () => {
  beforeEach(() => {
    useStore.setState({
      me: {
        handle: 'Amber Otter',
        role: 'user',
        is_moderator: false,
        is_owner: false,
        signed_in: false,
        discord_available: true,
      },
    })
  })

  it('shows the pseudonym without demanding an account', () => {
    renderNav()
    expect(screen.getByText('Amber Otter')).toBeInTheDocument()
  })

  it('points at the profile, where signing in now lives', () => {
    renderNav()
    expect(screen.getByRole('link', { name: /Amber Otter/ })).toHaveAttribute('href', '/profile')
  })
})

describe('when Discord is not configured', () => {
  it('still names you, because the pseudonym does not depend on Discord', () => {
    useStore.setState({
      me: {
        handle: 'Amber Otter',
        role: 'user',
        is_moderator: false,
        is_owner: false,
        signed_in: false,
        discord_available: false,
      },
    })
    renderNav()
    expect(screen.getByText('Amber Otter')).toBeInTheDocument()
  })
})

describe('signed in', () => {
  it('does not sign you out from here any more', async () => {
    const user = userEvent.setup()
    useStore.setState({
      me: {
        handle: 'Luka',
        role: 'user',
        is_moderator: false,
        is_owner: false,
        signed_in: true,
        discord_available: true,
      },
    })
    renderNav()
    // Clicking the name goes to the profile; signing out is a decision, and
    // making it one click from every page is how people do it by accident.
    await user.click(screen.getByRole('link', { name: /Luka/ }))
    expect(logout).not.toHaveBeenCalled()
  })

  it('shows the role when it is more than an ordinary user', () => {
    useStore.setState({
      me: {
        handle: 'Luka',
        role: 'owner',
        is_moderator: true,
        is_owner: true,
        signed_in: true,
        discord_available: true,
      },
    })
    renderNav()
    expect(screen.getByText('owner')).toBeInTheDocument()
  })

  it('does not show a role badge for an ordinary user', () => {
    useStore.setState({
      me: {
        handle: 'Luka',
        role: 'user',
        is_moderator: false,
        is_owner: false,
        signed_in: true,
        discord_available: true,
      },
    })
    renderNav()
    expect(screen.queryByText('user')).not.toBeInTheDocument()
  })
})

describe('folding on a narrow viewport', () => {
  /**
   * The bar was three rows deep on a phone: wordmark and four icon buttons,
   * then the search field, then a 160px sort select. Most of that was chrome
   * around icons, on the screen with the least room to give.
   */
  const mql = (matches) => ({
    matches,
    media: '',
    addEventListener: () => {},
    removeEventListener: () => {},
  })

  function renderNarrow(route = '/') {
    window.matchMedia = vi.fn().mockImplementation(() => mql(true))
    try {
      return renderNav(route)
    } finally {
      window.matchMedia = vi.fn().mockImplementation(() => mql(false))
    }
  }

  beforeEach(() => {
    useStore.setState({
      me: { handle: 'Amber Otter', role: 'user', is_moderator: false, signed_in: false },
    })
  })

  it('keeps the home link and drops the wordmark', () => {
    renderNarrow()
    expect(screen.getByRole('link', { name: /ImgManager home/i })).toBeInTheDocument()
    expect(screen.queryByText('ImgManager')).not.toBeInTheDocument()
  })

  it('folds the links behind one button, and unfolds them on demand', async () => {
    const user = userEvent.setup()
    renderNarrow()

    for (const name of [/Add Character/i, /Customs/i, /Amber Otter/]) {
      expect(screen.queryByRole('link', { name })).not.toBeInTheDocument()
    }

    const toggle = screen.getByRole('button', { name: /Show menu/i })
    expect(toggle).toHaveAttribute('aria-expanded', 'false')
    await user.click(toggle)

    for (const name of [/Add Character/i, /Customs/i, /Amber Otter/]) {
      expect(screen.getByRole('link', { name })).toBeInTheDocument()
    }
    expect(screen.getByRole('button', { name: /Hide menu/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    )
  })

  it('folds the filter to an arrow, and opens sort and search-by in one panel', async () => {
    const user = userEvent.setup()
    renderNarrow()

    expect(screen.queryByRole('menu', { name: /Filter/i })).not.toBeInTheDocument()
    // Folded, the control is the chevron alone: the current label is not shown.
    expect(document.querySelector('.filter-bar .sort-menu__current')).toBeNull()

    await user.click(screen.getByRole('button', { name: /Filter/i }))

    // The list belongs under the arrow, and every choice lives in the one panel.
    expect(screen.getByRole('menu', { name: /Filter/i })).toBeInTheDocument()
    const searchBy = within(screen.getByRole('group', { name: 'Search by' }))
    expect(searchBy.getByRole('menuitemradio', { name: 'Name' })).toBeInTheDocument()
    expect(searchBy.getByRole('menuitemradio', { name: 'Series' })).toBeInTheDocument()
    const sortBy = within(screen.getByRole('group', { name: 'Sort by' }))
    expect(sortBy.getByRole('menuitemradio', { name: 'Rank' })).toBeInTheDocument()
    expect(sortBy.getByRole('menuitemradio', { name: 'Alphabet' })).toBeInTheDocument()
    expect(sortBy.getByRole('menuitemradio', { name: 'Image count' })).toBeInTheDocument()
    expect(
      within(screen.getByRole('group', { name: 'Order' })).getAllByRole('menuitemradio'),
    ).toHaveLength(2)
    // The field stays where it is and simply narrows to make room.
    expect(screen.getByRole('searchbox')).toBeInTheDocument()

    await user.click(sortBy.getByRole('menuitemradio', { name: 'Alphabet' }))
    expect(useStore.getState().searchSort).toBe('alphabet')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('moves the search-by choice into the filter, out of the field', async () => {
    const user = userEvent.setup()
    renderNarrow()

    // No switch crammed into a phone-width field any more.
    expect(screen.queryByRole('radio', { name: 'Series' })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Filter/i }))
    await user.click(
      within(screen.getByRole('group', { name: 'Search by' })).getByRole('menuitemradio', {
        name: 'Series',
      }),
    )

    expect(useStore.getState().searchMode).toBe('series')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('keeps the search field while the menu has the bar, and drops the filter', async () => {
    const user = userEvent.setup()
    renderNarrow()
    expect(screen.getByRole('button', { name: /Filter/i })).toBeInTheDocument()

    // The field gives ground rather than leaving: it shrinks to a pill, and the
    // filter steps out on its own rather than competing with the menu. What
    // does leave is the filter control, because four links, a home button and a
    // menu button do not leave room for it as well.
    await user.click(screen.getByRole('button', { name: /Show menu/i }))
    expect(screen.getByRole('searchbox')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Filter/i })).not.toBeInTheDocument()
  })

  it('gets out of the way when you reach for the search field', async () => {
    const user = userEvent.setup()
    renderNarrow()
    await user.click(screen.getByRole('button', { name: /Show menu/i }))
    expect(screen.getByRole('link', { name: /Customs/i })).toBeInTheDocument()

    await user.click(screen.getByRole('searchbox'))
    expect(screen.queryByRole('link', { name: /Customs/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter/i })).toBeInTheDocument()
  })

  it('puts the menu button at the end of the bar', () => {
    renderNarrow()
    const rails = Array.from(document.querySelectorAll('.navbar-command > *'))
    const endRail = rails.at(-1)
    expect(endRail).toHaveClass('navbar-command__rail--end')
    expect(endRail.lastElementChild).toHaveClass('navbar-menu-toggle')
  })

  it('uses the same filter on a wide bar, not a separate select', () => {
    renderNav()
    expect(screen.getByText('ImgManager')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show menu/i })).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Customs/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Filter/i })).toBeInTheDocument()
    // There is room to spell out the current filter beside the arrow.
    expect(screen.getByText('Rank asc.')).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
  })
})

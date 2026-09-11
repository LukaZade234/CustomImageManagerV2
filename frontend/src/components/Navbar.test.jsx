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
import { render, screen } from '@testing-library/react'
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
import Navbar from './Navbar'

const renderNav = (route = '/') =>
  render(
    <MemoryRouter initialEntries={[route]}>
      <Navbar />
    </MemoryRouter>,
  )

beforeEach(() => {
  logout.mockClear()
  useStore.setState({ theme: 'system', searchQuery: '', searchMode: 'name', searchSort: 'rank' })
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

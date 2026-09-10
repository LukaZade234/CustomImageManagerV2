/**
 * The sign-in control.
 *
 * Sign-in is an upgrade, never a wall — so the thing worth pinning is that the
 * app is fully usable with no account, and that the control simply is not there
 * when Discord is not configured.
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

  it('offers sign-in as a link, because it is a full-page redirect', () => {
    renderNav()
    const link = screen.getByRole('link', { name: /sign in/i })
    expect(link).toHaveAttribute('href', expect.stringContaining('/api/auth/discord/start'))
  })

  it('carries the current page so you come back to it', () => {
    renderNav('/character/Rem')
    const href = screen.getByRole('link', { name: /sign in/i }).getAttribute('href')
    expect(href).toContain(encodeURIComponent('/character/Rem'))
  })
})

describe('when Discord is not configured', () => {
  it('does not offer sign-in at all', () => {
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
    expect(screen.queryByRole('link', { name: /sign in/i })).not.toBeInTheDocument()
    expect(screen.getByText('Amber Otter')).toBeInTheDocument()
  })
})

describe('signed in', () => {
  it('replaces the sign-in link with a sign-out control', async () => {
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
    expect(screen.queryByRole('link', { name: /sign in/i })).not.toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Luka/ }))
    expect(logout).toHaveBeenCalled()
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

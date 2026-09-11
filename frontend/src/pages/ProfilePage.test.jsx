/**
 * The profile page.
 *
 * Two things here are easy to get subtly wrong. The privacy switches must say
 * what they actually do — they hide a name at render time and never change what
 * is stored, which is what lets them be turned back off — and the hidden and
 * removed lists must actually act on the right image, because they are the only
 * way to reach those images at all.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  updateSettings: vi.fn(),
  getMyHidden: vi.fn(),
  getMyRemoved: vi.fn(),
  unhideImages: vi.fn().mockResolvedValue({}),
  restoreImages: vi.fn().mockResolvedValue({}),
  logout: vi.fn().mockResolvedValue({}),
}))

vi.mock('../api', () => ({ apiClient: api, getImageUrl: (p) => p || '' }))
vi.mock('../config', () => ({ apiUrl: (p) => p, signInUrl: (n) => `/start?next=${n}` }))

import { useStore } from '../store/useStore'
import ProfilePage from './ProfilePage'

const ME = {
  handle: 'Amber Otter',
  role: 'user',
  is_moderator: false,
  is_owner: false,
  signed_in: false,
  discord_available: true,
  settings: { hide_attribution: false, hide_from_leaderboard: false },
}

function show(me = ME) {
  useStore.setState({ me, theme: 'system', loadMe: vi.fn(), addToast: vi.fn() })
  render(
    <MemoryRouter>
      <ProfilePage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockClear?.()
  api.getMyHidden.mockResolvedValue([])
  api.getMyRemoved.mockResolvedValue([])
  api.updateSettings.mockImplementation((change) =>
    Promise.resolve({ settings: { ...ME.settings, ...change } }),
  )
})

describe('identity', () => {
  it('names you and explains that no account is needed', async () => {
    show()
    expect(await screen.findByText('Amber Otter')).toBeInTheDocument()
    expect(screen.getByText(/No account needed/i)).toBeInTheDocument()
  })

  it('warns that a cookie identity is fragile, and offers the fix', async () => {
    show()
    expect(await screen.findByText(/lives in a cookie/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Sign in with Discord/i })).toHaveAttribute(
      'href',
      '/start?next=/profile',
    )
  })

  it('drops the warning once you are signed in, and offers sign-out', async () => {
    show({ ...ME, signed_in: true })
    expect(await screen.findByText(/Signed in with Discord/i)).toBeInTheDocument()
    expect(screen.queryByText(/lives in a cookie/i)).not.toBeInTheDocument()

    await userEvent.click(screen.getByRole('button', { name: /Sign out/i }))
    expect(api.logout).toHaveBeenCalledTimes(1)
  })
})

describe('privacy', () => {
  it('states that the switches change display and not ownership', async () => {
    show()
    expect(await screen.findByText(/Neither changes what is stored/i)).toBeInTheDocument()
    expect(screen.getByText(/Moderators can still see who added an image/i)).toBeInTheDocument()
  })

  it('saves each switch independently', async () => {
    show()
    await userEvent.click(await screen.findByLabelText(/Do not show my name/i))
    expect(api.updateSettings).toHaveBeenCalledWith({ hide_attribution: true })

    await userEvent.click(screen.getByLabelText(/Keep me off the contributor ranking/i))
    expect(api.updateSettings).toHaveBeenCalledWith({ hide_from_leaderboard: true })
  })

  it('reflects settings that are already on', async () => {
    show({ ...ME, settings: { hide_attribution: true, hide_from_leaderboard: false } })
    expect(await screen.findByLabelText(/Do not show my name/i)).toBeChecked()
    expect(screen.getByLabelText(/Keep me off the contributor ranking/i)).not.toBeChecked()
  })

  it('puts the switch back if saving fails', async () => {
    api.updateSettings.mockRejectedValue(new Error('nope'))
    show()
    const toggle = await screen.findByLabelText(/Do not show my name/i)

    await userEvent.click(toggle)
    await waitFor(() => expect(toggle).not.toBeChecked())
  })
})

describe('theme', () => {
  it('offers all three states, which a cycling button could not show', async () => {
    show()
    expect(await screen.findByLabelText('Follow system')).toBeChecked()
    await userEvent.click(screen.getByLabelText('Dark'))
    expect(useStore.getState().theme).toBe('dark')
  })
})

describe('the lists nothing else can reach', () => {
  it('unhides an image and drops it from the list', async () => {
    api.getMyHidden.mockResolvedValue([
      { id: 7, url: 'https://cdn/a.png', thumb: '/thumbs/7.webp', character: 'Rem' },
    ])
    show()

    await userEvent.click(await screen.findByRole('button', { name: 'Unhide' }))
    expect(api.unhideImages).toHaveBeenCalledWith([7])
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: 'Unhide' })).not.toBeInTheDocument(),
    )
  })

  it('restores by character and URL, which is what the endpoint takes', async () => {
    api.getMyRemoved.mockResolvedValue([
      { id: 9, url: 'https://cdn/b.png', thumb: '/thumbs/9.webp', character: 'Emilia' },
    ])
    show()

    await userEvent.click(await screen.findByRole('button', { name: 'Restore' }))
    expect(api.restoreImages).toHaveBeenCalledWith('Emilia', ['https://cdn/b.png'])
  })

  it('links each image to the character holding it', async () => {
    api.getMyHidden.mockResolvedValue([
      { id: 7, url: 'https://cdn/a.png', thumb: '/thumbs/7.webp', character: 'Rem' },
    ])
    show()
    expect(await screen.findByRole('link', { name: 'Rem' })).toHaveAttribute(
      'href',
      '/character/Rem',
    )
  })

  it('says so plainly when there is nothing in either list', async () => {
    show()
    expect(await screen.findByText('Nothing hidden')).toBeInTheDocument()
    expect(screen.getByText('Nothing removed')).toBeInTheDocument()
  })
})

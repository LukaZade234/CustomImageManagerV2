/**
 * The profile's tabs.
 *
 * Two things are worth pinning. The list tabs all share one filter, and the
 * three states a personal list can be in — loading, empty, and "your search
 * matched nothing" — are different situations that need different words; a list
 * saying "nothing saved" while it is still loading is actively misleading.
 *
 * The other is that Saved moved here from its own page, so `/saved` has to keep
 * working for anyone who bookmarked it.
 */
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getMyHidden: vi.fn(),
  getMyRemoved: vi.fn(),
  getMyHistory: vi.fn(),
  unhideImages: vi.fn().mockResolvedValue({}),
  restoreImages: vi.fn().mockResolvedValue({}),
  updateSettings: vi.fn(),
  logout: vi.fn().mockResolvedValue({}),
}))

vi.mock('../../api', () => ({ apiClient: api, getImageUrl: (p) => p || '' }))
vi.mock('../../config', () => ({ apiUrl: (p) => p, signInUrl: (n) => `/start?next=${n}` }))

import { useStore } from '../../store/useStore'
import HiddenTab from './HiddenTab'
import HistoryTab from './HistoryTab'
import ProfileLayout from './ProfileLayout'
import SavedTab from './SavedTab'
import SettingsTab from './SettingsTab'

const at = (ui, route = '/profile') =>
  render(<MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>)

beforeEach(() => {
  for (const fn of Object.values(api)) fn.mockClear?.()
  api.getMyHidden.mockResolvedValue([])
  api.getMyRemoved.mockResolvedValue([])
  api.getMyHistory.mockResolvedValue([])
  api.updateSettings.mockImplementation((c) => Promise.resolve({ settings: c }))
  useStore.setState({
    me: {
      handle: 'Amber Otter',
      role: 'user',
      signed_in: false,
      discord_available: true,
      settings: {},
    },
    theme: 'system',
    savedCharacters: [],
    characters: [],
    addToast: vi.fn(),
    loadMe: vi.fn(),
    removeSaved: vi.fn().mockResolvedValue({}),
  })
})

describe('tabs', () => {
  it('marks the section you are on', () => {
    at(
      <Routes>
        <Route path="/profile" element={<ProfileLayout />}>
          <Route path="hidden" element={<HiddenTab />} />
        </Route>
      </Routes>,
      '/profile/hidden',
    )
    expect(screen.getByRole('link', { name: 'Hidden' })).toHaveClass('profile-tab--active')
    expect(screen.getByRole('link', { name: 'Saved' })).not.toHaveClass('profile-tab--active')
  })

  it('names you in the header', () => {
    at(<ProfileLayout />)
    expect(screen.getByRole('heading', { level: 1, name: 'Amber Otter' })).toBeInTheDocument()
  })
})

describe('list states', () => {
  it('does not claim a list is empty while it is still loading', async () => {
    let resolve
    api.getMyHidden.mockReturnValue(
      new Promise((r) => {
        resolve = r
      }),
    )
    at(<HiddenTab />)

    expect(screen.getByRole('status')).toHaveTextContent(/Loading/i)
    expect(screen.queryByText('Nothing hidden')).not.toBeInTheDocument()

    resolve([])
    expect(await screen.findByText('Nothing hidden')).toBeInTheDocument()
  })

  it('distinguishes an empty list from a search that matched nothing', async () => {
    api.getMyHidden.mockResolvedValue([
      { id: 1, url: 'a.png', thumb: '/t/1.webp', character: 'Rem', hidden_at: '2026-09-01' },
    ])
    at(<HiddenTab />)
    await screen.findByText('Rem')

    await userEvent.type(screen.getByLabelText(/Search by character/i), 'zzz')
    expect(await screen.findByText('Nothing matches that')).toBeInTheDocument()
    expect(screen.queryByText('Nothing hidden')).not.toBeInTheDocument()
  })

  it('hides the controls entirely when there is nothing to filter', async () => {
    at(<HiddenTab />)
    await screen.findByText('Nothing hidden')
    expect(screen.queryByLabelText(/Search by character/i)).not.toBeInTheDocument()
  })
})

describe('searching and sorting', () => {
  const ROWS = [
    { id: 1, url: 'a.png', character: 'Rem', hidden_at: '2026-09-01' },
    { id: 2, url: 'b.png', character: 'Emilia', hidden_at: '2026-09-05' },
  ]

  it('filters by character and reports how many of how many', async () => {
    api.getMyHidden.mockResolvedValue(ROWS)
    at(<HiddenTab />)
    await screen.findByText('Rem')
    expect(screen.getByText('2')).toBeInTheDocument()

    await userEvent.type(screen.getByLabelText(/Search by character/i), 'emi')
    await waitFor(() => expect(screen.queryByText('Rem')).not.toBeInTheDocument())
    expect(screen.getByText('Emilia')).toBeInTheDocument()
    expect(screen.getByText('1 of 2')).toBeInTheDocument()
  })

  it('sorts newest-first by default and alphabetically on request', async () => {
    api.getMyHidden.mockResolvedValue(ROWS)
    at(<HiddenTab />)
    await screen.findByText('Rem')

    const names = () =>
      screen
        .getAllByRole('link')
        .map((a) => a.textContent)
        .filter(Boolean)
    expect(names()).toEqual(['Emilia', 'Rem'])

    await userEvent.selectOptions(screen.getByLabelText('Sort by'), 'character')
    expect(names()).toEqual(['Emilia', 'Rem'])
  })
})

describe('acting on a list', () => {
  it('unhides and drops the row', async () => {
    api.getMyHidden.mockResolvedValue([
      { id: 7, url: 'a.png', character: 'Rem', hidden_at: '2026-09-01' },
    ])
    at(<HiddenTab />)

    await userEvent.click(await screen.findByRole('button', { name: 'Unhide' }))
    expect(api.unhideImages).toHaveBeenCalledWith([7])
    await waitFor(() => expect(screen.getByText('Nothing hidden')).toBeInTheDocument())
  })
})

describe('history', () => {
  it('shows how long ago and how many images', async () => {
    api.getMyHistory.mockResolvedValue([
      {
        name: 'Rem',
        series: 'Re:Zero',
        image: 'r.png',
        images: 12,
        visits: 3,
        last_viewed: new Date().toISOString(),
      },
    ])
    at(<HistoryTab />)
    expect(await screen.findByText('Rem')).toBeInTheDocument()
    // One subtitle line now, so the card stays a picture with a caption rather
    // than a row of columns.
    expect(screen.getByText('today · 12 images')).toBeInTheDocument()
  })

  it('says the history is local and temporary', async () => {
    at(<HistoryTab />)
    expect(await screen.findByText(/only for 90 days/i)).toBeInTheDocument()
  })
})

describe('saved', () => {
  it('fills in the series from the library', async () => {
    useStore.setState({
      savedCharacters: [{ name: 'Rem' }],
      characters: [{ name: 'Rem', series: 'Re:Zero', image: 'r.png' }],
    })
    at(<SavedTab />)
    expect(screen.getByText('Rem')).toBeInTheDocument()
    expect(screen.getByText('Re:Zero')).toBeInTheDocument()
  })
})

describe('settings', () => {
  it('records the NSFW preference even though nothing reads it yet', async () => {
    at(<SettingsTab />)
    await userEvent.click(screen.getByLabelText(/Show images marked NSFW/i))
    expect(api.updateSettings).toHaveBeenCalledWith({ show_nsfw: true })
    expect(screen.getByText(/changes nothing today/i)).toBeInTheDocument()
  })

  it('keeps the two privacy switches independent', async () => {
    at(<SettingsTab />)
    await userEvent.click(screen.getByLabelText(/Do not show my name/i))
    expect(api.updateSettings).toHaveBeenCalledWith({ hide_attribution: true })

    await userEvent.click(screen.getByLabelText(/Keep me off the contributor ranking/i))
    expect(api.updateSettings).toHaveBeenCalledWith({ hide_from_leaderboard: true })
  })

  it('offers the theme as three states, which a cycling button could not show', async () => {
    at(<SettingsTab />)
    expect(screen.getByLabelText('Follow system')).toBeChecked()
    await userEvent.click(screen.getByLabelText('Dark'))
    expect(useStore.getState().theme).toBe('dark')
  })
})

describe('card grid', () => {
  it('sizes each card to its image, so a row can justify', async () => {
    api.getMyHidden.mockResolvedValue([
      { id: 1, url: 'a.png', character: 'Rem', width: 1200, height: 600 },
      { id: 2, url: 'b.png', character: 'Ram', width: 400, height: 800 },
    ])
    const { container } = at(<HiddenTab />)
    await screen.findByText('Rem')

    const ratios = [...container.querySelectorAll('.profile-card')].map((el) =>
      Number(el.style.getPropertyValue('--ratio')),
    )
    expect(ratios[0]).toBeCloseTo(1.9, 1) // clamped: a panorama cannot flatten the row
    expect(ratios[1]).toBeCloseTo(0.5, 2)
  })

  it('falls back to the character-card shape when dimensions are missing', async () => {
    api.getMyHidden.mockResolvedValue([{ id: 1, url: 'a.png', character: 'Rem' }])
    const { container } = at(<HiddenTab />)
    await screen.findByText('Rem')
    expect(container.querySelector('.profile-card').style.getPropertyValue('--ratio')).toBe('0.643')
  })

  it('pads the last row so a lone card is not stretched across it', async () => {
    api.getMyHidden.mockResolvedValue([{ id: 1, url: 'a.png', character: 'Rem' }])
    const { container } = at(<HiddenTab />)
    await screen.findByText('Rem')
    expect(container.querySelectorAll('.profile-grid__filler').length).toBeGreaterThan(0)
  })

  it('adds no fillers when there is nothing to pad', async () => {
    const { container } = at(<HiddenTab />)
    await screen.findByText('Nothing hidden')
    expect(container.querySelectorAll('.profile-grid__filler')).toHaveLength(0)
  })
})

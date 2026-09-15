/**
 * The moderation surface.
 *
 * It is read-only and pull-based by design: nothing here is pending, nothing is
 * actionable, and the acting verbs stay on the character page. These tests pin
 * the parts that would quietly rot — the staff gate, the URL as the source of
 * truth, server-side filtering, and the three list states being told apart.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getMe: vi.fn(),
  listModerationUsers: vi.fn(),
  listModerationUserImages: vi.fn(),
  listModerationUserCharacters: vi.fn(),
  listModerationHistory: vi.fn(),
  restoreImages: vi.fn(),
  setModerationRole: vi.fn(),
  warnModerationUser: vi.fn(),
  suspendModerationUser: vi.fn(),
  banModerationUser: vi.fn(),
  liftModerationUser: vi.fn(),
  deleteModerationHistory: vi.fn(),
}))

vi.mock('../../api', () => ({
  getImageUrl: (p) => p || '',
  getPortraitUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: api,
}))

import RequireModerator from '../../components/RequireModerator'
import { renderWithQueryClient } from '../../test/renderWithQueryClient'
import ModerationPage from './ModerationPage'

const USERS = [
  {
    ref: 'ref-ada',
    handle: 'Ada Otter',
    role: 'user',
    signed_in: false,
    added: 2,
    removed: 0,
    last_at: '2026-01-02T00:00:00Z',
  },
  {
    ref: 'ref-bob',
    handle: 'Bob Falcon',
    role: 'moderator',
    signed_in: true,
    added: 0,
    removed: 3,
    last_at: '2026-01-01T00:00:00Z',
  },
]

function LocationProbe() {
  const location = useLocation()
  return <div data-testid="location">{`${location.pathname}${location.search}`}</div>
}

function renderModeration(route = '/moderation') {
  return renderWithQueryClient(
    <MemoryRouter initialEntries={[route]}>
      <LocationProbe />
      <Routes>
        <Route path="/" element={<div>home</div>} />
        <Route path="/character/:name" element={<div>character page</div>} />
        <Route
          path="/moderation"
          element={
            <RequireModerator>
              <ModerationPage />
            </RequireModerator>
          }
        />
      </Routes>
    </MemoryRouter>,
  )
}

const location = () => screen.getByTestId('location').textContent

beforeEach(() => {
  api.getMe.mockReset()
  api.listModerationUsers.mockReset()
  api.listModerationUserImages.mockReset()
  api.listModerationUserCharacters.mockReset()
  api.listModerationHistory.mockReset()
  api.restoreImages.mockReset()
  api.setModerationRole.mockReset()
  api.warnModerationUser.mockReset()
  api.suspendModerationUser.mockReset()
  api.banModerationUser.mockReset()
  api.liftModerationUser.mockReset()
  api.deleteModerationHistory.mockReset()
  api.getMe.mockResolvedValue({
    handle: 'Amber Otter',
    role: 'owner',
    is_moderator: true,
    is_owner: true,
  })
  api.listModerationUsers.mockResolvedValue({ items: USERS, total: USERS.length })
  api.listModerationUserImages.mockResolvedValue({
    items: [],
    total: 0,
    total_pages: 1,
    added: 2,
    removed: 3,
  })
  api.listModerationUserCharacters.mockResolvedValue({ items: [], total: 0, total_pages: 1 })
  api.listModerationHistory.mockResolvedValue({ items: [], total: 0 })
  api.restoreImages.mockResolvedValue({ success: true, restored: 1 })
  api.setModerationRole.mockResolvedValue({ success: true })
  api.warnModerationUser.mockResolvedValue({ success: true, id: 1 })
  api.suspendModerationUser.mockResolvedValue({ success: true, id: 2 })
  api.banModerationUser.mockResolvedValue({ success: true, id: 3 })
  api.liftModerationUser.mockResolvedValue({ success: true })
  api.deleteModerationHistory.mockResolvedValue({ success: true })
})

describe('the staff gate', () => {
  it('sends a non-moderator home without rendering the page', async () => {
    api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'user', is_moderator: false })
    renderModeration('/moderation?user=ref-ada')

    expect(await screen.findByText('home')).toBeInTheDocument()
    expect(screen.queryByRole('heading', { level: 1, name: /moderation/i })).not.toBeInTheDocument()
  })

  it('shows a moderator the contributor list', async () => {
    renderModeration()
    expect(await screen.findByRole('button', { name: /Ada Otter/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Bob Falcon/ })).toBeInTheDocument()
  })
})

describe('opening on the finder', () => {
  it('shows the search first, and the tabs only after a pick', async () => {
    const user = userEvent.setup()
    renderModeration()

    expect(await screen.findByLabelText('Search contributors by name')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Info' })).not.toBeInTheDocument()

    await user.click(await screen.findByRole('button', { name: /Ada Otter/ }))
    // The section tabs are the profile's own tab bar: links, with the active one
    // marked in the URL and named for assistive tech.
    expect(await screen.findByRole('link', { name: 'Info' })).toHaveAttribute(
      'aria-current',
      'page',
    )
    expect(screen.getByRole('link', { name: 'Images' })).toHaveAttribute(
      'href',
      expect.stringContaining('tab=images'),
    )
  })

  it('narrows the list by role', async () => {
    const user = userEvent.setup()
    renderModeration()
    await screen.findByRole('button', { name: /Ada Otter/ })

    await user.selectOptions(screen.getByLabelText('Role'), 'staff')

    expect(screen.getByRole('button', { name: /Bob Falcon/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Ada Otter/ })).not.toBeInTheDocument()
  })
})

describe('the URL is the source of truth', () => {
  it('puts the selected contributor in the URL, and renders them from it', async () => {
    const user = userEvent.setup()
    renderModeration()

    await user.click(await screen.findByRole('button', { name: /Ada Otter/ }))
    await waitFor(() => expect(location()).toContain('user=ref-ada'))
    expect(screen.getByRole('heading', { level: 2, name: 'Ada Otter' })).toBeInTheDocument()
  })

  it('opens on the finder when no contributor is selected', async () => {
    renderModeration('/moderation')
    expect(await screen.findByLabelText('Search contributors by name')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: 'Info' })).not.toBeInTheDocument()
  })

  it('switches to the Images tab through the link', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('link', { name: 'Images' })

    await user.click(screen.getByRole('link', { name: 'Images' }))
    await waitFor(() => expect(location()).toContain('tab=images'))
    expect(await screen.findByLabelText('Filter by character')).toBeInTheDocument()
  })

  it('asks the server for removals rather than filtering in the browser', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada&tab=images')
    await screen.findByRole('radio', { name: /Removed/ })

    api.listModerationUserImages.mockClear()
    await user.click(screen.getByRole('radio', { name: /Removed/ }))

    await waitFor(() =>
      expect(api.listModerationUserImages).toHaveBeenCalledWith({
        ref: 'ref-ada',
        state: 'removed',
        character: '',
        page: 1,
      }),
    )
    expect(location()).toContain('state=removed')
  })

  it('resets the page to one when the character filter changes', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada&tab=images&page=2')
    await screen.findByLabelText('Filter by character')

    await user.type(screen.getByLabelText('Filter by character'), 'Rem')

    await waitFor(
      () =>
        expect(api.listModerationUserImages).toHaveBeenLastCalledWith(
          expect.objectContaining({ character: 'Rem', page: 1 }),
        ),
      { timeout: 2000 },
    )
    expect(location()).not.toContain('page=2')
  })
})

describe('the three list states are distinguishable', () => {
  it('shows a loading list, not an empty one, while contributors load', async () => {
    api.listModerationUsers.mockReturnValue(new Promise(() => {}))
    renderModeration()
    // Wait past the role fetch, which renders nothing while it is pending.
    await screen.findByRole('heading', { level: 1, name: /moderation/i })
    expect(document.querySelector('.moderation-users__list')).toHaveAttribute('aria-busy', 'true')
    expect(screen.queryByText(/No contributors yet/i)).not.toBeInTheDocument()
  })

  it('shows the empty state when nobody has contributed', async () => {
    api.listModerationUsers.mockResolvedValue({ items: [], total: 0 })
    renderModeration()
    expect(await screen.findByText(/No contributors yet/i)).toBeInTheDocument()
  })

  it('offers a retry when the list fails, rather than a blank screen', async () => {
    api.listModerationUsers.mockRejectedValue(new Error('boom'))
    renderModeration()
    expect(await screen.findByText(/Could not load contributors/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Try again/i })).toBeInTheDocument()
  })

  it('shows the detail empty state when a chosen filter has nothing', async () => {
    api.listModerationUserImages.mockResolvedValue({
      items: [],
      total: 0,
      total_pages: 1,
      added: 2,
      removed: 3,
    })
    renderModeration('/moderation?user=ref-ada&tab=images&char=Nobody')
    expect(await screen.findByText(/Nothing matches that character/i)).toBeInTheDocument()
  })
})

describe('the profile and its work', () => {
  it('shows the contributor stats', async () => {
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })
    const profile = document.querySelector('.moderation-profile')
    expect(within(profile).getByText('Images')).toBeInTheDocument()
    expect(within(profile).getByText('Joined')).toBeInTheDocument()
    expect(within(profile).getByText('Last active')).toBeInTheDocument()
  })

  it('renders the person actions, all of them live', async () => {
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })
    for (const name of ['Warn', 'Suspend', 'Ban']) {
      expect(screen.getByRole('button', { name })).toBeEnabled()
    }
  })

  it('renders the image verbs, with permanent delete inert', async () => {
    api.listModerationUserImages.mockResolvedValue({
      items: [
        {
          id: 7,
          url: 'https://cdn/x.png',
          thumb: '/thumbs/7.webp',
          width: 1,
          height: 1,
          character: 'Rem',
          removed_at: '2026-01-01T00:00:00Z',
          removed_reason: 'spam',
        },
      ],
      total: 1,
      total_pages: 1,
      added: 2,
      removed: 1,
    })
    renderModeration('/moderation?user=ref-ada&tab=images&state=removed')
    expect(await screen.findByRole('button', { name: 'Restore' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Delete permanently' })).toBeDisabled()
  })

  it('renders the character view and refetches with the chosen sort', async () => {
    api.listModerationUserCharacters.mockResolvedValue({
      items: [
        { name: 'Rem', series: 'Re:Zero', rank: '3', image: 'x.png', image_thumb: '', count: 2 },
      ],
      total: 1,
      total_pages: 1,
    })
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada&tab=images')
    await screen.findByRole('radio', { name: 'Characters' })

    await user.click(screen.getByRole('radio', { name: 'Characters' }))
    expect(location()).toContain('view=characters')
    expect(await screen.findByText('Rem')).toBeInTheDocument()

    api.listModerationUserCharacters.mockClear()
    await user.click(screen.getByRole('radio', { name: 'Rank' }))
    await waitFor(() =>
      expect(api.listModerationUserCharacters).toHaveBeenCalledWith(
        expect.objectContaining({ sort: 'rank', order: 'asc', page: 1 }),
      ),
    )
  })

  it('drills into a character as a filter rather than leaving the page', async () => {
    api.listModerationUserCharacters.mockResolvedValue({
      items: [
        { name: 'Rem', series: 'Re:Zero', rank: '3', image: 'x.png', image_thumb: '', count: 2 },
      ],
      total: 1,
      total_pages: 1,
    })
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada&tab=images&view=characters')

    api.listModerationUserImages.mockClear()
    await user.click(await screen.findByRole('button', { name: /Rem/ }))

    await waitFor(() =>
      expect(api.listModerationUserImages).toHaveBeenCalledWith(
        expect.objectContaining({ character: 'Rem', page: 1 }),
      ),
    )
    expect(location()).toContain('char=Rem')
    expect(location()).not.toContain('view=characters')
    // It must not have navigated to the public character page.
    expect(screen.queryByText('character page')).not.toBeInTheDocument()
  })
})

describe('restore and role changes', () => {
  const removedImage = {
    id: 7,
    url: 'https://cdn/x.png',
    thumb: '/thumbs/7.webp',
    width: 1,
    height: 1,
    character: 'Rem',
    removed_at: '2026-01-01T00:00:00Z',
    removed_reason: 'spam',
  }

  it('restores a removed image through the existing endpoint', async () => {
    api.listModerationUserImages.mockResolvedValue({
      items: [removedImage],
      total: 1,
      total_pages: 1,
      added: 2,
      removed: 1,
    })
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada&tab=images&state=removed')

    await user.click(await screen.findByRole('button', { name: 'Restore' }))
    await waitFor(() =>
      expect(api.restoreImages).toHaveBeenCalledWith('Rem', ['https://cdn/x.png']),
    )
  })

  it('promotes a user only after the confirmation', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    await user.click(screen.getByRole('button', { name: 'Promote to moderator' }))
    // Nothing fires until the dialog is confirmed.
    expect(api.setModerationRole).not.toHaveBeenCalled()
    await user.click(await screen.findByRole('button', { name: 'Promote' }))
    await waitFor(() => expect(api.setModerationRole).toHaveBeenCalledWith('ref-ada', 'moderator'))
  })

  it('demotes a moderator only after the confirmation', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-bob')
    await screen.findByRole('heading', { level: 2, name: 'Bob Falcon' })

    await user.click(screen.getByRole('button', { name: 'Remove moderator role' }))
    await user.click(await screen.findByRole('button', { name: 'Remove' }))
    await waitFor(() => expect(api.setModerationRole).toHaveBeenCalledWith('ref-bob', 'user'))
  })

  it('cancelling the dialog changes nothing', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    await user.click(screen.getByRole('button', { name: 'Promote to moderator' }))
    await user.click(await screen.findByRole('button', { name: 'Cancel' }))
    expect(api.setModerationRole).not.toHaveBeenCalled()
  })

  it('does not offer a role change to a moderator', async () => {
    api.getMe.mockResolvedValue({
      handle: 'Amber Otter',
      role: 'moderator',
      is_moderator: true,
      is_owner: false,
    })
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })
    expect(screen.queryByRole('button', { name: 'Promote to moderator' })).not.toBeInTheDocument()
  })
})

describe('warning a contributor', () => {
  it('sends exactly the title and description the moderator writes', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    await user.click(screen.getByRole('button', { name: 'Warn' }))
    await user.type(await screen.findByLabelText('Title'), 'Keep it civil')
    await user.type(screen.getByLabelText('Description'), 'Third time this week.')
    await user.click(screen.getByRole('button', { name: 'Send warning' }))

    await waitFor(() =>
      expect(api.warnModerationUser).toHaveBeenCalledWith('ref-ada', {
        title: 'Keep it civil',
        body: 'Third time this week.',
      }),
    )
  })

  it('will not send a warning with no title', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    await user.click(screen.getByRole('button', { name: 'Warn' }))
    expect(await screen.findByRole('button', { name: 'Send warning' })).toBeDisabled()
    expect(api.warnModerationUser).not.toHaveBeenCalled()
  })
})

describe('the moderation history', () => {
  const entry = {
    id: 5,
    action: 'warn',
    title: 'Keep it civil',
    body: 'Third time this week.',
    created_at: '2026-01-03T00:00:00Z',
    actor_handle: 'Amber Otter',
  }

  it('lists what staff have sent, named and coloured by severity', async () => {
    api.listModerationHistory.mockResolvedValue({ items: [entry], total: 1 })
    renderModeration('/moderation?user=ref-ada')

    expect(await screen.findByText('Keep it civil')).toBeInTheDocument()
    expect(screen.getByText('Warning')).toBeInTheDocument()
    expect(screen.getByText(/by Amber Otter/)).toBeInTheDocument()
  })

  it('lets the owner delete a record, which takes the message with it', async () => {
    api.listModerationHistory.mockResolvedValue({ items: [entry], total: 1 })
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByText('Keep it civil')

    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(await screen.findByRole('button', { name: 'Delete record' }))
    await waitFor(() => expect(api.deleteModerationHistory).toHaveBeenCalledWith(5))
  })

  it('is view-only for a moderator', async () => {
    api.getMe.mockResolvedValue({
      handle: 'Amber Otter',
      role: 'moderator',
      is_moderator: true,
      is_owner: false,
    })
    api.listModerationHistory.mockResolvedValue({ items: [entry], total: 1 })
    renderModeration('/moderation?user=ref-ada')

    await screen.findByText('Keep it civil')
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })
})

describe('suspending and banning', () => {
  it('suspends with a duration chosen in the dialog', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    await user.click(screen.getByRole('button', { name: 'Suspend' }))
    await user.type(await screen.findByLabelText('Title'), 'Cool off')
    await user.selectOptions(screen.getByLabelText('Duration'), '7')
    await user.click(screen.getByRole('button', { name: /Send suspension/i }))

    await waitFor(() =>
      expect(api.suspendModerationUser).toHaveBeenCalledWith('ref-ada', {
        title: 'Cool off',
        body: '',
        days: 7,
      }),
    )
  })

  it('bans from the dialog', async () => {
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    await user.click(screen.getByRole('button', { name: 'Ban' }))
    await user.type(await screen.findByLabelText('Title'), 'Enough')
    await user.click(screen.getByRole('button', { name: /Send ban/i }))

    await waitFor(() =>
      expect(api.banModerationUser).toHaveBeenCalledWith('ref-ada', { title: 'Enough', body: '' }),
    )
  })

  it('shows the status, blocks re-banning, and lets the owner lift it', async () => {
    api.listModerationUsers.mockResolvedValue({
      items: [{ ...USERS[0], moderation_status: 'banned', moderation_reason: 'spam' }],
      total: 1,
    })
    const user = userEvent.setup()
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    expect(screen.getByText('Ban', { selector: '.ui-badge' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Ban' })).toBeDisabled()

    await user.click(screen.getByRole('button', { name: /Lift ban/i }))
    await user.click(await screen.findByRole('button', { name: 'Lift' }))
    await waitFor(() => expect(api.liftModerationUser).toHaveBeenCalledWith('ref-ada'))
  })

  it('does not offer Lift to a moderator, but shows the end date', async () => {
    api.getMe.mockResolvedValue({
      handle: 'Amber Otter',
      role: 'moderator',
      is_moderator: true,
      is_owner: false,
    })
    api.listModerationUsers.mockResolvedValue({
      items: [
        { ...USERS[0], moderation_status: 'suspended', moderation_until: '2026-02-01T00:00:00Z' },
      ],
      total: 1,
    })
    renderModeration('/moderation?user=ref-ada')
    await screen.findByRole('heading', { level: 2, name: 'Ada Otter' })

    expect(screen.getByText(/Suspended until/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Lift/i })).not.toBeInTheDocument()
  })
})

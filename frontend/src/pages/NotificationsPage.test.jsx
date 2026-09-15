/**
 * Notifications.
 *
 * A plain message log: messages to you, newest first, marked read on opening.
 * The owner alone gets the compose form at the top. Nothing here is a task, so
 * there is no pending count — just the unread state on your own rows.
 */
import { screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getMe: vi.fn(),
  getNotifications: vi.fn(),
  markNotificationsRead: vi.fn(),
  broadcastNotification: vi.fn(),
  dismissNotification: vi.fn(),
  deleteNotification: vi.fn(),
}))

vi.mock('../api', () => ({
  getImageUrl: (p) => p || '',
  getPortraitUrl: (p) => p || '',
  apiUrl: (p) => p,
  apiClient: api,
}))

import { renderWithQueryClient } from '../test/renderWithQueryClient'
import NotificationsPage from './NotificationsPage'

const ITEMS = [
  {
    id: 2,
    source: 'notification',
    pinned: false,
    kind: 'broadcast',
    title: 'Maintenance tonight',
    body: 'The site will be read-only for a while.',
    created_at: '2026-02-02T10:00:00Z',
    read_at: null,
  },
  {
    id: 1,
    source: 'notification',
    pinned: false,
    kind: 'mechanical',
    title: 'You are now a moderator',
    body: '',
    created_at: '2026-01-01T10:00:00Z',
    read_at: '2026-01-01T11:00:00Z',
  },
]

const PIN = {
  id: 9,
  source: 'pin',
  pinned: true,
  kind: 'broadcast',
  title: 'Welcome',
  body: 'Read me',
  created_at: '2026-03-03T10:00:00Z',
  read_at: null,
}

function renderPage() {
  return renderWithQueryClient(
    <MemoryRouter>
      <NotificationsPage />
    </MemoryRouter>,
  )
}

beforeEach(() => {
  api.getMe.mockReset()
  api.getNotifications.mockReset()
  api.markNotificationsRead.mockReset()
  api.broadcastNotification.mockReset()
  api.dismissNotification.mockReset()
  api.deleteNotification.mockReset()
  api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'user', is_moderator: false })
  api.getNotifications.mockResolvedValue({ items: ITEMS, unread: 1 })
  api.markNotificationsRead.mockResolvedValue({ success: true })
  api.broadcastNotification.mockResolvedValue({ success: true, sent: 3 })
  api.dismissNotification.mockResolvedValue({ success: true })
  api.deleteNotification.mockResolvedValue({ success: true, removed: 2 })
})

describe('the notification list', () => {
  it('shows each message with its title and body', async () => {
    renderPage()
    expect(await screen.findByText('Maintenance tonight')).toBeInTheDocument()
    expect(screen.getByText('The site will be read-only for a while.')).toBeInTheDocument()
    expect(screen.getByText('You are now a moderator')).toBeInTheDocument()
  })

  it('marks everything read on opening', async () => {
    renderPage()
    await screen.findByText('Maintenance tonight')
    await waitFor(() => expect(api.markNotificationsRead).toHaveBeenCalledTimes(1))
  })

  it('does not mark read when there is nothing unread', async () => {
    api.getNotifications.mockResolvedValue({ items: ITEMS, unread: 0 })
    renderPage()
    await screen.findByText('Maintenance tonight')
    expect(api.markNotificationsRead).not.toHaveBeenCalled()
  })

  it('shows an empty state when there is nothing', async () => {
    api.getNotifications.mockResolvedValue({ items: [], unread: 0 })
    renderPage()
    expect(await screen.findByText(/Nothing yet/i)).toBeInTheDocument()
  })
})

describe('the owner compose form', () => {
  it('is not shown to anyone but the owner', async () => {
    renderPage()
    await screen.findByText('Maintenance tonight')
    expect(screen.queryByText(/Send a notification/i)).not.toBeInTheDocument()
  })

  it('lets the owner send to a chosen audience', async () => {
    api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'owner', is_owner: true })
    const user = userEvent.setup()
    renderPage()

    const compose = await screen.findByText(/Send a notification/i)
    const card = compose.closest('.ui-card')
    await user.click(within(card).getByRole('radio', { name: 'Moderators' }))
    await user.type(within(card).getByLabelText('Notification title'), 'Staff only')
    await user.type(within(card).getByLabelText('Message (optional)'), 'Heads up')
    await user.click(within(card).getByRole('button', { name: /^Send$/i }))

    await waitFor(() =>
      expect(api.broadcastNotification).toHaveBeenCalledWith({
        audience: 'moderators',
        title: 'Staff only',
        body: 'Heads up',
        pinned: false,
      }),
    )
  })

  it('sends a pinned message when the pin box is ticked', async () => {
    api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'owner', is_owner: true })
    const user = userEvent.setup()
    renderPage()

    const compose = await screen.findByText(/Send a notification/i)
    const card = compose.closest('.ui-card')
    await user.type(within(card).getByLabelText('Notification title'), 'Welcome')
    await user.click(within(card).getByRole('checkbox'))
    await user.click(within(card).getByRole('button', { name: /^Send$/i }))

    await waitFor(() =>
      expect(api.broadcastNotification).toHaveBeenCalledWith(
        expect.objectContaining({ title: 'Welcome', pinned: true }),
      ),
    )
  })
})

describe('dismiss and delete', () => {
  const withItems = (items) => api.getNotifications.mockResolvedValue({ items, unread: 0 })

  it('offers Dismiss on a normal message and removes it', async () => {
    withItems([ITEMS[0]])
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Maintenance tonight')
    await user.click(screen.getByRole('button', { name: 'Dismiss' }))
    await waitFor(() => expect(api.dismissNotification).toHaveBeenCalledWith({ id: 2 }))
  })

  it('shows a pinned message with a badge and no Dismiss', async () => {
    withItems([PIN])
    renderPage()

    expect(await screen.findByText('Welcome')).toBeInTheDocument()
    expect(screen.getByText('Pinned')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Dismiss' })).not.toBeInTheDocument()
    // A pin the reader has not opened yet is unread like any other message.
    expect(document.querySelector('.notification')).toHaveClass('notification--unread')
  })

  it('does not offer Delete to a non-owner', async () => {
    withItems([ITEMS[0]])
    renderPage()
    await screen.findByText('Maintenance tonight')
    expect(screen.queryByRole('button', { name: 'Delete' })).not.toBeInTheDocument()
  })

  it('lets the owner delete a broadcast after a confirmation', async () => {
    api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'owner', is_owner: true })
    withItems([ITEMS[0]])
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Maintenance tonight')
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: /^Delete$/ }),
    )
    await waitFor(() =>
      expect(api.deleteNotification).toHaveBeenCalledWith({ source: 'notification', id: 2 }),
    )
  })

  it('deletes a pin by its own source', async () => {
    api.getMe.mockResolvedValue({ handle: 'Amber Otter', role: 'owner', is_owner: true })
    withItems([PIN])
    const user = userEvent.setup()
    renderPage()

    await screen.findByText('Welcome')
    await user.click(screen.getByRole('button', { name: 'Delete' }))
    await user.click(
      within(await screen.findByRole('dialog')).getByRole('button', { name: /^Delete$/ }),
    )
    await waitFor(() =>
      expect(api.deleteNotification).toHaveBeenCalledWith({ source: 'pin', id: 9 }),
    )
  })
})

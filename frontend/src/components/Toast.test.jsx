import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useStore } from '../store/useStore'
import Toast from './Toast'

/**
 * Also serves as the harness smoke test: it proves React 19, testing-library 16
 * and zustand 5 work together after the Phase 0 upgrades.
 */

beforeEach(() => {
  useStore.setState({ toasts: [] })
})

afterEach(() => {
  vi.useRealTimers()
})

describe('Toast', () => {
  it('renders nothing when there are no toasts', () => {
    const { container } = render(<Toast />)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows a queued message', () => {
    useStore.getState().addToast('Image imported from the web.', 'success')
    render(<Toast />)
    expect(screen.getByText('Image imported from the web.')).toBeInTheDocument()
  })

  it('dismisses from its own control, which the keyboard can reach', async () => {
    const user = userEvent.setup()
    useStore.getState().addToast('Upload failed', 'error')
    render(<Toast />)

    await user.click(screen.getByRole('button', { name: /Dismiss notification/i }))

    expect(screen.queryByText('Upload failed')).not.toBeInTheDocument()
    expect(useStore.getState().toasts).toHaveLength(0)
  })

  it('is announced as a status, not offered as a control', async () => {
    // The toast used to be role="button" wrapping the Undo button -- a button
    // inside a button. Screen readers announce a toast; they do not press it.
    useStore.getState().addToast('3 images removed', 'info')
    render(<Toast />)

    expect(screen.getByRole('status')).toHaveTextContent('3 images removed')
  })

  it('undo no longer has to fight the toast for the click', async () => {
    const user = userEvent.setup()
    const onUndo = vi.fn().mockResolvedValue(undefined)
    useStore.getState().addToast('3 images removed', 'info', { onUndo })
    render(<Toast />)

    await user.click(screen.getByRole('button', { name: 'Undo' }))
    expect(onUndo).toHaveBeenCalledTimes(1)
  })

  it('runs the undo callback and then dismisses', async () => {
    const user = userEvent.setup()
    const onUndo = vi.fn().mockResolvedValue(undefined)
    useStore.getState().addToast('3 images removed', 'info', { onUndo })
    render(<Toast />)

    await user.click(screen.getByRole('button', { name: 'Undo' }))

    expect(onUndo).toHaveBeenCalledOnce()
    expect(useStore.getState().toasts).toHaveLength(0)
  })

  it('offers no undo affordance when none was supplied', () => {
    useStore.getState().addToast('Saved', 'success')
    render(<Toast />)
    expect(screen.queryByRole('button', { name: 'Undo' })).not.toBeInTheDocument()
  })

  it('auto-dismisses once its timeout elapses', () => {
    vi.useFakeTimers()
    useStore.getState().addToast('Transient', 'info')
    expect(useStore.getState().toasts).toHaveLength(1)

    vi.advanceTimersByTime(60_000)

    expect(useStore.getState().toasts).toHaveLength(0)
  })
})

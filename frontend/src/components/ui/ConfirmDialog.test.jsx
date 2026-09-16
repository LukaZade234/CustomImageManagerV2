/**
 * The confirmation step.
 *
 * This is the only confirmation path in the app — there is no `window.confirm`
 * anywhere — and it sits in front of irreversible actions like a permanent
 * delete. So the thing worth pinning is that it cannot confirm by accident:
 * cancel cancels, and dismissing it counts as cancel, not as confirm.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ConfirmDialog from './ConfirmDialog'

function setup(props = {}) {
  const onConfirm = vi.fn()
  const onCancel = vi.fn()
  render(
    <ConfirmDialog
      title="Remove 3 images?"
      body="They can be restored from the Removed drawer."
      onConfirm={onConfirm}
      onCancel={onCancel}
      {...props}
    />,
  )
  return { onConfirm, onCancel }
}

describe('ConfirmDialog', () => {
  it('asks the question and explains the consequence', () => {
    setup()

    expect(screen.getByRole('dialog')).toHaveAccessibleName('Remove 3 images?')
    expect(screen.getByText(/restored from the Removed drawer/)).toBeInTheDocument()
  })

  it('confirms', async () => {
    const { onConfirm, onCancel } = setup()

    await userEvent.click(screen.getByRole('button', { name: 'Confirm' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onCancel).not.toHaveBeenCalled()
  })

  it('cancels', async () => {
    const { onConfirm, onCancel } = setup()

    await userEvent.click(screen.getByRole('button', { name: 'Cancel' }))

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('takes the caller’s wording for both buttons', () => {
    setup({ confirmLabel: 'Delete forever', cancelLabel: 'Keep them' })

    expect(screen.getByRole('button', { name: 'Delete forever' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Keep them' })).toBeInTheDocument()
  })

  it('treats a dismissal as cancel, never as confirm', async () => {
    const { onConfirm, onCancel } = setup()

    await userEvent.keyboard('{Escape}')

    expect(onCancel).toHaveBeenCalledTimes(1)
    expect(onConfirm).not.toHaveBeenCalled()
  })
})

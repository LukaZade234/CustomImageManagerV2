/**
 * Every dialog in the app is this component, so a way out of it is the one
 * thing it cannot be missing.
 *
 * It was. The comment in the source said the dialog "has a visible close
 * button" and none was ever rendered, which left three real ways to dismiss —
 * the backdrop, Escape, and whatever buttons the caller happened to pass. On a
 * phone the backdrop is a 16px band around a dialog that fills the screen,
 * Escape needs a keyboard, and a caller with a long list and no footer (the
 * removed-images drawer) had none of the three.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Modal from './Modal'

function setup(props = {}) {
  const onClose = vi.fn()
  render(
    <Modal onClose={onClose} title="Removed from Lucy" {...props}>
      <p>Body</p>
    </Modal>,
  )
  return onClose
}

describe('Modal', () => {
  it('offers a close button whenever it has a title to sit beside', async () => {
    const onClose = setup()
    await userEvent.click(screen.getByRole('button', { name: /close/i }))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('keeps that button out of the scrolling body, beside the title', () => {
    setup()
    const header = document.querySelector('.ui-modal__header')
    // A long list scrolls under the header rather than taking it with it, which
    // is what put the title — and would have put the close button — off screen.
    expect(header).toContainElement(screen.getByRole('button', { name: /close/i }))
    expect(header).toContainElement(screen.getByRole('heading', { name: 'Removed from Lucy' }))
    expect(document.querySelector('.ui-modal__body')).not.toContainElement(
      screen.getByRole('button', { name: /close/i }),
    )
  })

  it('still closes on Escape and on the backdrop', async () => {
    const onClose = setup()
    await userEvent.keyboard('{Escape}')
    expect(onClose).toHaveBeenCalledTimes(1)

    await userEvent.click(document.querySelector('.ui-modal-backdrop'))
    expect(onClose).toHaveBeenCalledTimes(2)
  })

  it('does not close when the dialog itself is clicked', async () => {
    const onClose = setup()
    await userEvent.click(screen.getByText('Body'))
    expect(onClose).not.toHaveBeenCalled()
  })

  it('names itself by its title, for anyone listening', () => {
    setup()
    expect(screen.getByRole('dialog')).toHaveAccessibleName('Removed from Lucy')
  })
})

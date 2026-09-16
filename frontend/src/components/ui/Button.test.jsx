/**
 * The one button in the system.
 *
 * It is used on every screen, and two of its behaviours are load-bearing rather
 * than cosmetic: a button that is `loading` must not be pressable again (that is
 * a double-submit), and `as` must let navigation wear the styling as a real
 * link. Both are pinned here; the class names are not, because they are not the
 * contract anyone depends on.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import Button from './Button'

describe('Button', () => {
  it('is a button and reports a click', async () => {
    const onClick = vi.fn()
    render(<Button onClick={onClick}>Save</Button>)

    const button = screen.getByRole('button', { name: 'Save' })
    expect(button).toHaveAttribute('type', 'button')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('cannot be pressed again while it is loading', async () => {
    const onClick = vi.fn()
    render(
      <Button loading onClick={onClick}>
        Saving…
      </Button>,
    )

    const button = screen.getByRole('button', { name: 'Saving…' })
    expect(button).toBeDisabled()
    expect(button).toHaveAttribute('aria-busy', 'true')
    await userEvent.click(button)
    expect(onClick).not.toHaveBeenCalled()
  })

  it('is disabled when told to be', () => {
    render(<Button disabled>Nope</Button>)
    expect(screen.getByRole('button', { name: 'Nope' })).toBeDisabled()
  })

  it('can wear the styling as a link without becoming a button', () => {
    render(
      <Button as="a" href="/add">
        Add
      </Button>,
    )

    const link = screen.getByRole('link', { name: 'Add' })
    expect(link).toHaveAttribute('href', '/add')
    expect(link).not.toHaveAttribute('type')
  })
})

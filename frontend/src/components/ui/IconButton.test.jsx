/**
 * An icon-only button.
 *
 * With no visible text, its accessible name is the only way a screen reader can
 * describe it, which is why `label` is required rather than optional. That name
 * is also the default tooltip, so a sighted person hovering gets the same word.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import IconButton from './IconButton'

const SVG = <svg aria-hidden="true" />

describe('IconButton', () => {
  it('always has an accessible name, even with no visible text', () => {
    render(<IconButton label="Close">{SVG}</IconButton>)
    expect(screen.getByRole('button', { name: 'Close' })).toBeInTheDocument()
  })

  it('uses the label as the tooltip unless told otherwise', () => {
    render(<IconButton label="Close">{SVG}</IconButton>)
    expect(screen.getByRole('button', { name: 'Close' })).toHaveAttribute('title', 'Close')
  })

  it('reports clicks', async () => {
    const onClick = vi.fn()
    render(
      <IconButton label="Close" onClick={onClick}>
        {SVG}
      </IconButton>,
    )

    await userEvent.click(screen.getByRole('button', { name: 'Close' }))

    expect(onClick).toHaveBeenCalledTimes(1)
  })
})

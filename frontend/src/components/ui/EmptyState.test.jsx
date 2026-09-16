/** Explains why a region is empty, and offers the way out of it if there is one. */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import EmptyState from './EmptyState'

describe('EmptyState', () => {
  it('explains the emptiness', () => {
    render(<EmptyState title="Nothing hidden" />)
    expect(screen.getByText('Nothing hidden')).toBeInTheDocument()
  })

  it('offers the way out when there is one', () => {
    render(
      <EmptyState
        title="Nothing hidden"
        description="Images you hide appear here."
        action={<button type="button">Browse</button>}
      />,
    )

    expect(screen.getByText('Images you hide appear here.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Browse' })).toBeInTheDocument()
  })

  it('leaves the description and action out when not given', () => {
    render(<EmptyState title="Nothing hidden" />)
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})

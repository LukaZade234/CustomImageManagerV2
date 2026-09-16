/** One surface recipe, so that every panel on the site is the same panel. */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Card from './Card'

describe('Card', () => {
  it('renders its content', () => {
    render(<Card>Hello</Card>)
    expect(screen.getByText('Hello')).toBeInTheDocument()
  })

  it('can be a different element when the layout needs one', () => {
    render(
      <Card as="section" aria-label="Highlights">
        x
      </Card>,
    )
    expect(screen.getByRole('region', { name: 'Highlights' })).toBeInTheDocument()
  })
})

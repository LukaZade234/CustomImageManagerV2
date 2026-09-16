/** A small inline count or status label. Barely more than a span. */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Badge from './Badge'

describe('Badge', () => {
  it('shows its text', () => {
    render(<Badge>3 removed</Badge>)
    expect(screen.getByText('3 removed')).toBeInTheDocument()
  })
})

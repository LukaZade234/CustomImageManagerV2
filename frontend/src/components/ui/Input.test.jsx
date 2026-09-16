/** A native input that can mark itself invalid for screen readers. */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { createRef } from 'react'
import { describe, expect, it, vi } from 'vitest'
import Input from './Input'

describe('Input', () => {
  it('accepts typing and reports it', async () => {
    const onChange = vi.fn()
    render(<Input aria-label="Name" onChange={onChange} />)

    await userEvent.type(screen.getByLabelText('Name'), 'Re')

    expect(onChange).toHaveBeenCalled()
  })

  it('marks itself invalid only when asked', () => {
    const { rerender } = render(<Input aria-label="Rank" />)
    expect(screen.getByLabelText('Rank')).not.toHaveAttribute('aria-invalid')

    rerender(<Input aria-label="Rank" invalid />)
    expect(screen.getByLabelText('Rank')).toHaveAttribute('aria-invalid', 'true')
  })

  it('forwards its ref to the input', () => {
    const ref = createRef()
    render(<Input aria-label="Name" ref={ref} />)

    expect(ref.current).toBe(screen.getByLabelText('Name'))
  })
})

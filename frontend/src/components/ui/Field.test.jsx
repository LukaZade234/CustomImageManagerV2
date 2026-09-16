/**
 * Label, control and hint wired together.
 *
 * The point of this component is that the label actually labels something and
 * the hint is announced *with* the control. A broken `aria-describedby` is
 * invisible until a screen reader meets it, so it is asserted through what the
 * assistive tree reports rather than by inspecting ids.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import Field from './Field'

describe('Field', () => {
  it('labels the control it wraps', () => {
    render(<Field label="Character name">{({ id }) => <input id={id} />}</Field>)

    expect(screen.getByLabelText('Character name')).toBeInTheDocument()
  })

  it('announces the hint with the control', () => {
    render(
      <Field label="Character name" hint="As it appears in Mudae">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    )

    expect(screen.getByLabelText('Character name')).toHaveAccessibleDescription(
      'As it appears in Mudae',
    )
  })

  it('replaces the hint with the error when there is one', () => {
    render(
      <Field label="Rank" hint="A number" error="Must be a number">
        {({ id, describedBy }) => <input id={id} aria-describedby={describedBy} />}
      </Field>,
    )

    expect(screen.getByLabelText('Rank')).toHaveAccessibleDescription('Must be a number')
    expect(screen.queryByText('A number')).not.toBeInTheDocument()
  })

  it('labels a control that brings its own id', () => {
    render(
      <Field label="Series" htmlFor="series-field">
        <input id="series-field" />
      </Field>,
    )

    expect(screen.getByLabelText('Series')).toBeInTheDocument()
  })
})

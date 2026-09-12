/**
 * The one hand-built menu in the app.
 *
 * Everywhere else a native `<select>` does this, and it brings arrow keys,
 * Escape, a click outside and focus handling with it. The phone bar cannot use
 * one — the platform answers with a sheet in the middle of the screen, detached
 * from the control that opened it — so all of that has to be written out, and
 * written out is exactly the kind of thing that quietly stops working.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { SortMenu } from './SortMenu'

const OPTIONS = [
  { value: 'rank', label: 'Rank (High-Low)' },
  { value: 'name', label: 'Name (A-Z)' },
  { value: 'series', label: 'Series (A-Z)' },
]

/** Renders with `open` held by the harness, the way SearchBar holds it. */
function setup({ value = 'rank', open = false } = {}) {
  const onOpenChange = vi.fn()
  const onChange = vi.fn()
  const { rerender } = render(
    <div>
      <button type="button">outside</button>
      <SortMenu
        options={OPTIONS}
        value={value}
        open={open}
        onOpenChange={onOpenChange}
        onChange={onChange}
      />
    </div>,
  )
  const show = (next) =>
    rerender(
      <div>
        <button type="button">outside</button>
        <SortMenu
          options={OPTIONS}
          value={value}
          open={next}
          onOpenChange={onOpenChange}
          onChange={onChange}
        />
      </div>,
    )
  return { onOpenChange, onChange, show }
}

const toggle = () => screen.getByRole('button', { name: /^Sort:/i })

describe('SortMenu', () => {
  it('is an arrow until it is asked for', () => {
    setup()
    expect(toggle()).toHaveAccessibleName('Sort: Rank (High-Low). Change.')
    expect(toggle()).toHaveAttribute('aria-expanded', 'false')
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
  })

  it('opens on click and names what is currently chosen', async () => {
    const { onOpenChange } = setup()
    await userEvent.click(toggle())
    expect(onOpenChange).toHaveBeenCalledWith(true)
  })

  it('marks the current choice rather than leaving you to remember it', () => {
    setup({ open: true })
    expect(screen.getByRole('menuitemradio', { name: /Rank/ })).toHaveAttribute(
      'aria-checked',
      'true',
    )
    expect(screen.getByRole('menuitemradio', { name: /Name/ })).toHaveAttribute(
      'aria-checked',
      'false',
    )
  })

  it('starts focus on the current choice, so the list opens where you are', () => {
    setup({ open: true })
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /Rank/ }))
  })

  it('chooses, then closes', async () => {
    const { onChange, onOpenChange } = setup({ open: true })
    await userEvent.click(screen.getByRole('menuitemradio', { name: /Series/ }))
    expect(onChange).toHaveBeenCalledWith('series')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('walks the options with the arrow keys', async () => {
    setup({ open: true })
    await userEvent.keyboard('{ArrowDown}')
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /Name/ }))
    await userEvent.keyboard('{ArrowUp}')
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /Rank/ }))
  })

  it('wraps around rather than stopping at the ends', async () => {
    setup({ open: true })
    await userEvent.keyboard('{ArrowUp}')
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /Series/ }))
  })

  it('closes on Escape', async () => {
    const { onOpenChange } = setup({ open: true })
    await userEvent.keyboard('{Escape}')
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('closes when something outside it is touched', async () => {
    const { onOpenChange } = setup({ open: true })
    await userEvent.click(screen.getByRole('button', { name: 'outside' }))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('stops listening for that once it is closed', async () => {
    const { onOpenChange, show } = setup({ open: true })
    show(false)
    onOpenChange.mockClear()
    await userEvent.click(screen.getByRole('button', { name: 'outside' }))
    expect(onOpenChange).not.toHaveBeenCalled()
  })
})

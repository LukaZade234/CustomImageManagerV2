/**
 * The duplicate dialog. Its job is to show *what* the refused upload collided
 * with, and to make "upload a second copy anyway" a deliberate click rather than
 * an accident.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../config', () => ({ thumbUrl: (t) => `thumb:${t}` }))
vi.mock('../api', () => ({ getImageUrl: (u) => `full:${u}` }))

import DuplicateDialog from './DuplicateDialog'

const existing = {
  id: 7,
  character: 'Rem',
  url: 'https://cdn/a.png',
  thumb: 'thumbs/7.webp',
  state: 'active',
  owner: 'Someone',
  added_at: '2026-01-02T00:00:00Z',
}

function renderDialog(items, overrides = {}) {
  const onSkip = vi.fn()
  const onUploadAnyway = vi.fn()
  const onRestore = vi.fn().mockResolvedValue(undefined)
  render(
    <DuplicateDialog
      items={items}
      onSkip={onSkip}
      onUploadAnyway={onUploadAnyway}
      onRestore={onRestore}
      {...overrides}
    />,
  )
  return { onSkip, onUploadAnyway, onRestore }
}

describe('DuplicateDialog', () => {
  it('shows the thing being added beside the copy already here', () => {
    renderDialog([{ file: new Blob(['x']), label: 'a.png', existing, alsoOn: [] }])
    expect(screen.getByText(/you’re adding/i)).toBeInTheDocument()
    expect(screen.getAllByText(/already here/i).length).toBeGreaterThan(0)
    expect(screen.getByText(/Rem/)).toBeInTheDocument()
    expect(screen.getByText(/Someone/)).toBeInTheDocument()
  })

  it('uploads anyway on request', async () => {
    const { onUploadAnyway } = renderDialog([
      { file: new Blob(['x']), label: 'a.png', existing, alsoOn: [] },
    ])
    await userEvent.click(screen.getByRole('button', { name: /upload anyway/i }))
    expect(onUploadAnyway).toHaveBeenCalled()
  })

  it('skips on request', async () => {
    const { onSkip } = renderDialog([
      { file: new Blob(['x']), label: 'a.png', existing, alsoOn: [] },
    ])
    await userEvent.click(screen.getByRole('button', { name: /skip/i }))
    expect(onSkip).toHaveBeenCalled()
  })

  it('offers to restore a removed copy instead of adding a second one', async () => {
    const removed = { ...existing, state: 'removed' }
    const { onRestore } = renderDialog([
      { file: new Blob(['x']), label: 'a.png', existing: removed, alsoOn: [] },
    ])
    expect(screen.getByText(/was removed from the gallery/i)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /restore it/i }))
    expect(onRestore).toHaveBeenCalledWith(removed)
  })

  it('does not offer restore for an active copy', () => {
    renderDialog([{ file: new Blob(['x']), label: 'a.png', existing, alsoOn: [] }])
    expect(screen.queryByRole('button', { name: /restore it/i })).not.toBeInTheDocument()
  })

  it('notes when the same picture is used on another character', () => {
    renderDialog([
      {
        url: 'https://example.test/pic.png',
        label: 'pic.png',
        existing,
        alsoOn: [{ id: 9, character: 'Emilia' }],
      },
    ])
    expect(screen.getByText(/also used on Emilia/i)).toBeInTheDocument()
  })
})

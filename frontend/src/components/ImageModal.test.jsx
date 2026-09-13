/**
 * Stacked dialogs.
 *
 * The report dialog opens over the image lightbox, so two dialogs are mounted
 * at once. Both register document-level key handlers, and before the topmost
 * registry the consequences were silent: Escape closed the report dialog *and*
 * the lightbox together, and the lightbox's arrow keys kept driving the image
 * behind the dialog. These tests pin topmost-only behaviour.
 */
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { describe, expect, it, vi } from 'vitest'
import ImageModal from './ImageModal'
import Modal from './ui/Modal'

function Harness({ onPrev, onNext }) {
  const [lightbox, setLightbox] = useState(true)
  const [report, setReport] = useState(false)
  return (
    <>
      {lightbox && (
        <ImageModal
          images={['https://cdn/a.png', 'https://cdn/b.png']}
          currentIndex={0}
          onClose={() => setLightbox(false)}
          onPrev={onPrev}
          onNext={onNext}
          onReport={() => setReport(true)}
        />
      )}
      {report && (
        <Modal title="Report this image" onClose={() => setReport(false)}>
          <p>Reasons</p>
        </Modal>
      )}
    </>
  )
}

describe('ImageModal stacked dialogs', () => {
  it('closes only the report dialog on Escape, then the lightbox', async () => {
    render(<Harness onPrev={vi.fn()} onNext={vi.fn()} />)
    await userEvent.click(screen.getByRole('button', { name: /^report$/i }))

    expect(screen.getByRole('dialog', { name: /report this image/i })).toBeTruthy()
    expect(screen.getByRole('dialog', { name: /image viewer/i })).toBeTruthy()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: /report this image/i })).toBeNull()
    expect(screen.getByRole('dialog', { name: /image viewer/i })).toBeTruthy()

    await userEvent.keyboard('{Escape}')
    expect(screen.queryByRole('dialog', { name: /image viewer/i })).toBeNull()
  })

  it('does not let the lightbox arrow keys fire while the report dialog is open', async () => {
    const onNext = vi.fn()
    const onPrev = vi.fn()
    render(<Harness onPrev={onPrev} onNext={onNext} />)
    await userEvent.click(screen.getByRole('button', { name: /^report$/i }))

    await userEvent.keyboard('{ArrowRight}')
    await userEvent.keyboard('{ArrowLeft}')
    expect(onNext).not.toHaveBeenCalled()
    expect(onPrev).not.toHaveBeenCalled()

    await userEvent.keyboard('{Escape}')
    await userEvent.keyboard('{ArrowRight}')
    expect(onNext).toHaveBeenCalledTimes(1)
  })
})

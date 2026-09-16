import { useEffect, useState } from 'react'
import { getImageUrl } from '../api'
import { thumbUrl } from '../config'
import { Button, Modal } from './ui'

/**
 * The same picture, already here.
 *
 * The server refuses to upload a duplicate because ImgChest cannot delete the
 * only image in a post — a second copy would be orphaned there forever. So the
 * default is to stop, and this dialog is where the visitor sees *what* it
 * collided with and decides whether the copy was intentional.
 *
 * `items` are the refusals, each `{ file }` or `{ url }` for the thing being
 * added, plus `{ label, existing, alsoOn }`. A file gets a local preview through
 * an object URL; a dragged URL is shown as-is. When the copy already here was
 * *removed*, the right answer is usually to restore it rather than upload a
 * second one, so that gets its own button.
 */

function formatDate(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

function AddingPreview({ preview }) {
  const [src, setSrc] = useState(null)

  useEffect(() => {
    if (typeof Blob !== 'undefined' && preview instanceof Blob) {
      const objectUrl = URL.createObjectURL(preview)
      setSrc(objectUrl)
      return () => URL.revokeObjectURL(objectUrl)
    }
    setSrc(typeof preview === 'string' ? preview : null)
    return undefined
  }, [preview])

  if (!src) return <div className="duplicate-dialog__image duplicate-dialog__image--empty" />
  return <img className="duplicate-dialog__image" src={src} alt="" />
}

function ExistingPreview({ existing }) {
  const src = existing?.thumb ? thumbUrl(existing.thumb) : getImageUrl(existing?.url)
  if (!src) return <div className="duplicate-dialog__image duplicate-dialog__image--empty" />
  return <img className="duplicate-dialog__image" src={src} alt="" />
}

export default function DuplicateDialog({ items, onSkip, onUploadAnyway, onRestore }) {
  const [restoringId, setRestoringId] = useState(null)
  const elsewhere = [
    ...new Set(
      items.flatMap((item) => (item.alsoOn || []).map((m) => m.character)).filter(Boolean),
    ),
  ]

  const restore = async (existing) => {
    setRestoringId(existing.id)
    try {
      await onRestore(existing)
    } finally {
      setRestoringId(null)
    }
  }

  return (
    <Modal
      onClose={onSkip}
      title="Already in this gallery"
      titleId="duplicate-dialog-title"
      size="md"
      footer={
        <>
          <Button onClick={onSkip}>Skip</Button>
          <Button onClick={onUploadAnyway}>Upload anyway</Button>
        </>
      }
    >
      <p className="duplicate-dialog__lead">
        {items.length === 1
          ? 'This image is already here.'
          : `${items.length} of these images are already here.`}{' '}
        Adding it again would upload a second copy to ImgChest, so it was not added.
      </p>

      <ul className="duplicate-dialog__list">
        {items.map((item, index) => (
          <li key={item.file?.name || item.url || index} className="duplicate-dialog__item">
            <div className="duplicate-dialog__pair">
              <figure className="duplicate-dialog__pane">
                <figcaption className="duplicate-dialog__label">You&rsquo;re adding</figcaption>
                <AddingPreview preview={item.file || item.url} />
                <span className="duplicate-dialog__caption">{item.label}</span>
              </figure>
              <figure className="duplicate-dialog__pane">
                <figcaption className="duplicate-dialog__label">Already here</figcaption>
                <ExistingPreview existing={item.existing} />
                <span className="duplicate-dialog__caption">
                  {item.existing?.character}
                  {item.existing?.owner ? ` · ${item.existing.owner}` : ''}
                  {item.existing?.added_at ? ` · ${formatDate(item.existing.added_at)}` : ''}
                </span>
              </figure>
            </div>
            {item.existing?.state === 'removed' && (
              <div className="duplicate-dialog__actions">
                <p className="duplicate-dialog__note">
                  That copy was removed from the gallery. It still exists, so restoring it keeps a
                  single copy instead of adding another.
                </p>
                <Button
                  size="sm"
                  loading={restoringId === item.existing.id}
                  onClick={() => restore(item.existing)}
                >
                  Restore it
                </Button>
              </div>
            )}
          </li>
        ))}
      </ul>

      {elsewhere.length > 0 && (
        <p className="duplicate-dialog__note">
          The same picture is also used on {elsewhere.join(', ')}.
        </p>
      )}
    </Modal>
  )
}

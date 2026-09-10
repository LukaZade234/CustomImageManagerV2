import { useEffect, useState } from 'react'
import { getImageUrl } from '../api'
import { apiUrl } from '../config'
import { Button, EmptyState, Modal } from './ui'

/**
 * Everything removed from this character, and a way to put it back.
 *
 * Nothing is ever hard-deleted — ImgChest keeps the file regardless — so this
 * list is complete by construction. Restoring is open to anyone on purpose: it
 * is not destructive, and a removal that was wrong should be cheap for the next
 * person to undo (DECISIONS.md section 1).
 */
export default function RemovedDrawer({ characterName, items, onRestore, onClose }) {
  const [busy, setBusy] = useState(null)
  const [rows, setRows] = useState(items)

  useEffect(() => setRows(items), [items])

  const restore = async (url) => {
    setBusy(url)
    try {
      await onRestore(url)
      setRows((current) => current.filter((row) => row.url !== url))
    } finally {
      setBusy(null)
    }
  }

  return (
    <Modal onClose={onClose} title={`Removed from ${characterName}`} size="lg">
      {rows.length === 0 ? (
        <EmptyState
          title="Nothing has been removed"
          description="Removed images land here instead of being deleted, so they can always be brought back."
        />
      ) : (
        <ul className="removed-drawer__list">
          {rows.map((row) => (
            <li key={row.id} className="removed-drawer__item">
              <img
                src={row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url)}
                alt=""
                className="removed-drawer__thumb"
              />
              <div className="removed-drawer__meta">
                <p className="text-meta">
                  {row.reason?.startsWith('reported:')
                    ? `Removed after reports — ${row.reason.replace('reported: ', '')}`
                    : row.removed_by
                      ? `Removed by ${row.removed_by}`
                      : 'Removed'}
                </p>
              </div>
              <Button size="sm" loading={busy === row.url} onClick={() => restore(row.url)}>
                Restore
              </Button>
            </li>
          ))}
        </ul>
      )}
    </Modal>
  )
}

import { useEffect, useRef } from 'react'
import { Button } from './ui'

/**
 * The gallery's mode bar: one group of buttons per gallery mode.
 *
 * Lifted out of CharacterPage, which was carrying ~230 lines of button markup
 * inline. It holds no state — the page owns `mode` and every handler — so the
 * prop list is long by necessity: each button needs its own action, and a flat
 * list keeps every one greppable from the call site rather than hiding them
 * inside a bag object that only this component ever reads.
 */
export function GalleryToolbar({
  mode,
  selectedUrls,
  totalCount,
  mineSelected,
  othersSelected,
  hiddenCount,
  showHidden,
  uploadBusy,
  onEnterRemove,
  onEnterDownload,
  onEnterReorder,
  onExitMode,
  onCancelReorder,
  onDoneReorder,
  onSelectAll,
  onClearSelection,
  onGenerateAiCommand,
  onRemoveSelected,
  onHideSelected,
  onDownloadSelected,
  onUnhideAll,
  onToggleShowHidden,
  onOpenRemovedDrawer,
  onAddImage,
}) {
  const group = useRef(null)
  const previousMode = useRef(mode)

  /**
   * Keep focus inside the toolbar across a mode change.
   *
   * Entering a mode unmounts the button that was just clicked -- the browse
   * group only renders while mode === 'browse' -- so the browser drops focus to
   * <body>. A keyboard user was returned to the top of the document on every
   * mode change, five times a session, and had to re-traverse the navbar and
   * the header to get back. Moving focus to the new group's first control keeps
   * them where they were working.
   */
  useEffect(() => {
    if (previousMode.current === mode) return
    previousMode.current = mode
    const first = group.current?.querySelector('button:not(:disabled)')
    // Only steal focus if the user was already in the toolbar; a mode entered
    // from the character header should not yank focus down the page.
    if (first && group.current?.contains(document.activeElement)) first.focus()
    else if (first && document.activeElement === document.body) first.focus()
  }, [mode])

  const aiMode = mode === 'ai'
  const deleteMode = mode === 'remove'
  const downloadMode = mode === 'download'
  const reorderMode = mode === 'reorder'

  return (
    <div className="char-custom-toolbar-actions" ref={group}>
      {aiMode && (
        <>
          <Button variant="success" size="sm" onClick={onGenerateAiCommand}>
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
              <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
            </svg>
            Copy Command ({selectedUrls.length || totalCount})
          </Button>
          <Button variant="secondary" size="sm" onClick={onSelectAll}>
            Select All
          </Button>
          <Button variant="secondary" size="sm" onClick={onExitMode}>
            Cancel
          </Button>
        </>
      )}
      {deleteMode && (
        <>
          <Button
            variant="danger"
            size="sm"
            onClick={onRemoveSelected}
            disabled={mineSelected.length === 0}
            title={
              mineSelected.length === 0
                ? 'You can only remove images you added'
                : 'Remove your own images'
            }
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            Remove mine ({mineSelected.length})
          </Button>
          <Button
            size="sm"
            onClick={onHideSelected}
            disabled={othersSelected.length === 0}
            title={
              othersSelected.length === 0
                ? "Select someone else's image to hide it"
                : 'Hide these for you only. Nobody else is affected.'
            }
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
              <line x1="1" y1="1" x2="23" y2="23" />
            </svg>
            Hide theirs ({othersSelected.length})
          </Button>
          <Button variant="secondary" size="sm" onClick={onExitMode}>
            Cancel
          </Button>
        </>
      )}
      {downloadMode && (
        <>
          <Button
            variant="primary"
            size="sm"
            onClick={onDownloadSelected}
            disabled={selectedUrls.length === 0}
            title={
              selectedUrls.length === 0
                ? 'Select images first'
                : 'Choose a folder and save files there'
            }
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download ({selectedUrls.length})
          </Button>
          <Button variant="secondary" size="sm" onClick={onSelectAll}>
            Select All
          </Button>
          <Button variant="secondary" size="sm" onClick={onExitMode}>
            Cancel
          </Button>
        </>
      )}
      {reorderMode && (
        <>
          <Button variant="secondary" size="sm" onClick={onClearSelection}>
            Clear selection
          </Button>
          {/* Not "Cancel": this writes to the server and throws the session's
              work away, while "Done" is the one that costs nothing. */}
          <Button variant="secondary" size="sm" onClick={onCancelReorder}>
            Discard changes
          </Button>
          <Button variant="primary" size="sm" onClick={onDoneReorder}>
            Done
          </Button>
        </>
      )}
      {mode === 'browse' && hiddenCount > 0 && (
        <Button
          size="sm"
          onClick={onToggleShowHidden}
          title="Images you have hidden are only hidden for you"
        >
          {showHidden ? 'Hide them again' : `Show ${hiddenCount} hidden`}
        </Button>
      )}
      {mode === 'browse' && showHidden && (
        <Button size="sm" onClick={onUnhideAll}>
          Unhide all ({hiddenCount})
        </Button>
      )}
      {mode === 'browse' && (
        <Button
          variant="ghost"
          size="sm"
          onClick={onOpenRemovedDrawer}
          title="Nothing is deleted permanently — see what was removed and put it back"
        >
          Removed
        </Button>
      )}
      {mode === 'browse' && (
        <>
          <Button variant="secondary" size="sm" onClick={onEnterRemove}>
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
            </svg>
            Remove or hide
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={onEnterDownload}
            title="Download selected custom images to a folder"
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download
          </Button>
          <Button variant="secondary" size="sm" onClick={onEnterReorder}>
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <polyline points="5 9 2 12 5 15" />
              <polyline points="9 5 12 2 15 5" />
              <polyline points="19 9 22 12 19 15" />
              <polyline points="9 19 12 22 15 19" />
              <line x1="2" y1="12" x2="22" y2="12" />
              <line x1="12" y1="2" x2="12" y2="22" />
            </svg>
            Reorder
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={uploadBusy}
            onClick={onAddImage}
            title="Add Custom Image"
          >
            <svg
              aria-hidden="true"
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            Add Image
          </Button>
        </>
      )}
    </div>
  )
}

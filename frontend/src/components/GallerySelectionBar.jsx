import { useEffect, useRef } from 'react'
import { Button, IconButton } from './ui'

/**
 * The bar that appears along the bottom while a gallery mode is open.
 *
 * These controls used to live in the heading row above the gallery, and a
 * character can hold 256 images. So selecting anything below the fold meant
 * scrolling back up to act on it and back down to carry on — for every image.
 * A sticky rule was tried and could not work: the toolbar sits inside the
 * heading row, and a sticky element can only travel as far as its own parent,
 * which is one row tall. It scrolled away with the heading every time.
 *
 * Fixed to the viewport instead, so the way out of a mode and the things you
 * can do with a selection are always the same distance away. It is also where
 * there is room: the heading row could only wrap the controls onto more lines,
 * which is what made a full selection feel like a wall of buttons.
 *
 * Weight does the rest of the work. The count is text, the selection helpers
 * are ghosts, and only the verbs read as buttons — one solid, the destructive
 * one in danger. Seven controls of identical weight is a wall; the same seven
 * sorted into three tiers is a sentence.
 */
export function GallerySelectionBar({
  mode,
  selectedCount,
  totalCount,
  mineCount,
  mineSelectedCount,
  othersSelectedCount,
  onSelectAll,
  onSelectMine,
  onClearSelection,
  onGenerateAiCommand,
  onDownloadSelected,
  onRemoveSelected,
  onHideSelected,
  onExitMode,
  onCancelReorder,
  onDoneReorder,
}) {
  const bar = useRef(null)
  const hasSelection = selectedCount > 0

  /**
   * Never leave the keyboard stranded when the bar's contents change.
   *
   * Two things change them: opening a mode, which mounts the bar, and making
   * the first selection, which swaps the helpers for the verbs. Either way the
   * control that was just used can disappear, and the browser answers that by
   * dropping focus to <body> — at the top of a document whose gallery may be
   * several screens long.
   */
  useEffect(() => {
    if (document.activeElement && document.activeElement !== document.body) return
    bar.current?.querySelector('button:not(:disabled)')?.focus()
  }, [])

  const previousHasSelection = useRef(hasSelection)
  useEffect(() => {
    if (previousHasSelection.current === hasSelection) return
    previousHasSelection.current = hasSelection
    if (document.activeElement && document.activeElement !== document.body) return
    bar.current?.querySelector('button:not(:disabled)')?.focus()
  }, [hasSelection])

  const selecting = mode === 'select'

  return (
    /* A landmark rather than a bare div: it appears mid-task, sits away from
       the images it governs, and is the only way out of the mode, so it should
       be something a screen reader can jump to by name. */
    <section
      className="gallery-action-bar"
      ref={bar}
      aria-label={selecting ? 'Selection actions' : 'Reorder actions'}
    >
      <div className="gallery-action-bar__inner">
        {selecting ? (
          <>
            <p className="gallery-action-bar__count">
              <strong>{selectedCount}</strong> of {totalCount} selected
            </p>
            <div className="gallery-action-bar__helpers">
              {/*
                One control that flips, rather than a Select all replaced by a
                Clear: the replacement unmounts the button under the caret.
                Both ends stay enabled — clearing an empty selection is
                harmless, and a button that disables itself when clicked drops
                focus just as surely as one that unmounts.
              */}
              <Button
                variant="ghost"
                size="sm"
                onClick={hasSelection ? onClearSelection : onSelectAll}
              >
                {hasSelection ? 'Clear' : `Select all (${totalCount})`}
              </Button>
              {mineCount > 0 && !hasSelection && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={onSelectMine}
                  title="Select every image you added, which are the ones you can remove"
                >
                  Select mine ({mineCount})
                </Button>
              )}
            </div>
            {hasSelection && (
              <div className="gallery-action-bar__verbs">
                {/* No count on these two: they act on everything selected, and
                    the bar already says how many that is. Remove and Hide keep
                    theirs because they act on a *part* of the selection, which
                    is the one number you cannot read off the count. */}
                <Button variant="primary" size="sm" onClick={onGenerateAiCommand}>
                  Copy $ai command
                </Button>
                <Button variant="secondary" size="sm" onClick={onDownloadSelected}>
                  Download
                </Button>
                {/* Absent rather than disabled. You can only remove what you
                    added and only hide what you did not, so each verb appears
                    exactly when the selection holds something it can act on. */}
                {othersSelectedCount > 0 && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={onHideSelected}
                    title="Hide these for you only. Nobody else is affected."
                  >
                    Hide ({othersSelectedCount})
                  </Button>
                )}
                {mineSelectedCount > 0 && (
                  <Button
                    variant="danger"
                    size="sm"
                    onClick={onRemoveSelected}
                    title="Removed images go to the Removed list, where anyone can restore them"
                  >
                    Remove ({mineSelectedCount})
                  </Button>
                )}
              </div>
            )}
            <IconButton className="gallery-action-bar__close" label="Done" onClick={onExitMode}>
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </IconButton>
          </>
        ) : (
          <>
            <p className="gallery-action-bar__count">
              {selectedCount > 0
                ? `Moving ${selectedCount} together`
                : 'Drag an image, or use the arrow keys'}
            </p>
            <div className="gallery-action-bar__helpers">
              <Button variant="ghost" size="sm" onClick={onClearSelection}>
                Clear
              </Button>
            </div>
            <div className="gallery-action-bar__verbs">
              {/* Not "Cancel": this writes to the server and throws the
                  session's work away, while "Done" is the one that costs
                  nothing. */}
              <Button variant="secondary" size="sm" onClick={onCancelReorder}>
                Discard changes
              </Button>
              <Button variant="primary" size="sm" onClick={onDoneReorder}>
                Done
              </Button>
            </div>
          </>
        )}
      </div>
    </section>
  )
}

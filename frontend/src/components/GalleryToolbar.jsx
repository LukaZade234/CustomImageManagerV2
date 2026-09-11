import { useEffect, useRef } from 'react'
import { Button } from './ui'

/**
 * The gallery's mode bar.
 *
 * There used to be five modes, and four of them — $ai command, remove, hide,
 * download — were the same interaction wearing different hats: pick images,
 * then do one thing to them. The gallery already knew this (`selecting` was one
 * boolean OR'd together from four), but the toolbar did not, so browse carried
 * seven equal-weight buttons whose only job was to decide which verb you would
 * be allowed to use once you had chosen. Worse, the verb was committed before
 * the selection existed, which is how "Remove mine (0)" came to be a button you
 * could enter, look at, and leave without it ever being usable.
 *
 * Now there is one selection, and the verbs appear once there is something for
 * them to act on. A verb you cannot use is not disabled, it is absent: you
 * cannot select an image you do not own and then wonder why Remove is greyed
 * out, because Remove only exists while your own images are in the selection.
 *
 * Reorder stays its own mode. It is the one place where the *pointer* means
 * something different — a drag moves an image rather than selecting it — so
 * folding it in would make a stray drag silently rearrange the gallery.
 *
 * Holds no state: the page owns `mode`, the selection and every handler.
 */

/** The toolbar's icons are all 16px, 2px stroke, no fill. */
function Icon({ children }) {
  return (
    <svg
      aria-hidden="true"
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
    >
      {children}
    </svg>
  )
}

const SelectIcon = () => (
  <Icon>
    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
    <polyline points="8 12 11 15 16 9" />
  </Icon>
)

const CopyIcon = () => (
  <Icon>
    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </Icon>
)

const DownloadIcon = () => (
  <Icon>
    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
    <polyline points="7 10 12 15 17 10" />
    <line x1="12" y1="15" x2="12" y2="3" />
  </Icon>
)

const TrashIcon = () => (
  <Icon>
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
  </Icon>
)

const HideIcon = () => (
  <Icon>
    <path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24" />
    <line x1="1" y1="1" x2="23" y2="23" />
  </Icon>
)

const ReorderIcon = () => (
  <Icon>
    <polyline points="5 9 2 12 5 15" />
    <polyline points="9 5 12 2 15 5" />
    <polyline points="19 9 22 12 19 15" />
    <polyline points="9 19 12 22 15 19" />
    <line x1="2" y1="12" x2="22" y2="12" />
    <line x1="12" y1="2" x2="12" y2="22" />
  </Icon>
)

const PlusIcon = () => (
  <Icon>
    <line x1="12" y1="5" x2="12" y2="19" />
    <line x1="5" y1="12" x2="19" y2="12" />
  </Icon>
)

export function GalleryToolbar({
  mode,
  selectedUrls,
  totalCount,
  mineCount,
  mineSelected,
  othersSelected,
  hiddenCount,
  showHidden,
  uploadBusy,
  onEnterSelect,
  onEnterReorder,
  onExitMode,
  onCancelReorder,
  onDoneReorder,
  onSelectAll,
  onSelectMine,
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
   * mode change and had to re-traverse the navbar and the header to get back.
   * Moving focus to the new group's first control keeps them where they were
   * working.
   *
   * Within a mode nothing that can hold focus is allowed to disappear: the
   * select-all control flips its own label rather than swapping places with a
   * clear button, and the helpers stay enabled rather than disabling themselves
   * out from under the caret. Only the verbs come and go, and they arrive after
   * a selection is made somewhere else.
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

  const selectMode = mode === 'select'
  const reorderMode = mode === 'reorder'
  const browseMode = mode === 'browse'
  const selectedCount = selectedUrls.length

  return (
    <div className="char-custom-toolbar-actions" ref={group}>
      {selectMode && (
        <>
          {/* Not a live region: each image already announces its own pressed
              state as it is selected, so repeating the running total would say
              everything twice. */}
          <span className="toolbar-selection-count">
            {selectedCount} of {totalCount} selected
          </span>
          {/*
            One control that flips, rather than a Select all that is replaced by
            a Clear: the replacement unmounts the button under the caret, which
            is the same focus loss the mode switches used to cause. It also stays
            enabled at both ends — clearing an empty selection is harmless, and a
            button that disables itself when clicked drops focus just as surely
            as one that unmounts.
          */}
          <Button
            variant="secondary"
            size="sm"
            onClick={selectedCount ? onClearSelection : onSelectAll}
          >
            {selectedCount ? 'Clear selection' : `Select all (${totalCount})`}
          </Button>
          {mineCount > 0 && (
            <Button
              variant="secondary"
              size="sm"
              onClick={onSelectMine}
              title="Select every image you added, which are the ones you can remove"
            >
              Select mine ({mineCount})
            </Button>
          )}
          {selectedCount > 0 && (
            <>
              <Button variant="primary" size="sm" onClick={onGenerateAiCommand}>
                <CopyIcon />
                Copy $ai command ({selectedCount})
              </Button>
              <Button variant="secondary" size="sm" onClick={onDownloadSelected}>
                <DownloadIcon />
                Download ({selectedCount})
              </Button>
            </>
          )}
          {/* Absent rather than disabled. You can only remove what you added and
              only hide what you did not, so each verb appears exactly when the
              selection contains something it can act on. */}
          {mineSelected.length > 0 && (
            <Button
              variant="danger"
              size="sm"
              onClick={onRemoveSelected}
              title="Removed images go to the Removed list, where anyone can restore them"
            >
              <TrashIcon />
              Remove ({mineSelected.length})
            </Button>
          )}
          {othersSelected.length > 0 && (
            <Button
              size="sm"
              onClick={onHideSelected}
              title="Hide these for you only. Nobody else is affected."
            >
              <HideIcon />
              Hide ({othersSelected.length})
            </Button>
          )}
          <Button variant="secondary" size="sm" onClick={onExitMode}>
            Done
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
      {browseMode && (
        <>
          {hiddenCount > 0 && (
            <Button
              size="sm"
              onClick={onToggleShowHidden}
              title="Images you have hidden are only hidden for you"
            >
              {showHidden ? 'Hide them again' : `Show ${hiddenCount} hidden`}
            </Button>
          )}
          {showHidden && (
            <Button size="sm" onClick={onUnhideAll}>
              Unhide all ({hiddenCount})
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            onClick={onOpenRemovedDrawer}
            title="Nothing is deleted permanently — see what was removed and put it back"
          >
            Removed
          </Button>
          {/* The three things you can do here, rather than the seven verbs you
              could once commit to before knowing what you were committing them
              to. Everything the other four buttons offered now lives behind
              Select, where the images decide which verbs make sense. */}
          <Button
            variant="secondary"
            size="sm"
            disabled={totalCount === 0}
            onClick={onEnterSelect}
            title={
              totalCount === 0
                ? 'Add an image first'
                : 'Pick images to copy, download, remove or hide'
            }
          >
            <SelectIcon />
            Select
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={totalCount < 2}
            onClick={onEnterReorder}
            title={totalCount < 2 ? 'Reordering needs at least two images' : 'Change the order'}
          >
            <ReorderIcon />
            Reorder
          </Button>
          <Button
            variant="secondary"
            size="sm"
            disabled={uploadBusy}
            onClick={onAddImage}
            title="Add a custom image"
          >
            <PlusIcon />
            Add image
          </Button>
        </>
      )}
    </div>
  )
}

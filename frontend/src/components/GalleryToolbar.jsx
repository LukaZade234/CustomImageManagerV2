import { Button } from './ui'

/**
 * The row of controls beside the "Custom Images" heading.
 *
 * Browse only. The controls for an open mode moved to GallerySelectionBar,
 * which is fixed to the bottom of the viewport: they are the way out of a mode
 * and the things you can do with a selection, and up here they scrolled away
 * the moment you looked at an image below the fold.
 *
 * What is left is the three things you can start, plus the door back to
 * whatever has been removed. There were seven, four of which only chose which
 * verb you would be allowed to use once you had selected something — a decision
 * you cannot sensibly make before the selection exists.
 *
 * Holds no state: the page owns the mode and every handler.
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
  totalCount,
  hiddenCount,
  showHidden,
  uploadBusy,
  onEnterSelect,
  onEnterReorder,
  onUnhideAll,
  onToggleShowHidden,
  onOpenRemovedDrawer,
  onAddImage,
}) {
  return (
    <div className="char-custom-toolbar-actions">
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
      <Button
        variant="secondary"
        size="sm"
        disabled={totalCount === 0}
        onClick={onEnterSelect}
        title={totalCount === 0 ? 'Add an image first' : 'Pick images to download, remove or hide'}
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
    </div>
  )
}

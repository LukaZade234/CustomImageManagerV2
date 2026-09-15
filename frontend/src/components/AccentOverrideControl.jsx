import { Button } from './ui'

/**
 * The staff-only accent control on a character page.
 *
 * The measured accent is usually right, but not always: a character read as
 * green can be out-voted by blonde hair on area. This lets a moderator or the
 * owner overrule it by picking a pixel straight off the art. Enabling "Pick"
 * arms the portrait and the gallery; the next click samples that pixel and
 * saves it, with no separate confirm step.
 */
export default function AccentOverrideControl({ accent }) {
  if (!accent?.canEdit) return null

  return (
    <div className="accent-override">
      <span className="accent-override__label">Accent</span>
      <span
        className={`accent-override__swatch ${accent.seed ? '' : 'is-empty'}`}
        style={accent.seed ? { backgroundColor: accent.seed } : undefined}
        aria-hidden="true"
      />
      <span className="accent-override__state">{accent.manual ? 'Manual' : 'Measured'}</span>
      <Button
        variant="ghost"
        size="sm"
        aria-pressed={accent.pickMode}
        disabled={accent.busy}
        onClick={accent.onTogglePick}
      >
        {accent.pickMode ? 'Cancel pick' : 'Pick from image'}
      </Button>
      {accent.manual && (
        <Button variant="ghost" size="sm" disabled={accent.busy} onClick={accent.onClear}>
          Reset to measured
        </Button>
      )}
      {accent.pickMode && (
        <span className="accent-override__hint" role="status">
          Click a pixel on the portrait or a gallery image
        </span>
      )}
    </div>
  )
}

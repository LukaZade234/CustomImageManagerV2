import { cx } from '../../utils/cx'

/**
 * The Name / Series switch, previously copy-pasted between SearchBar and
 * CustomsPage as `<span role="button">` pairs with an Enter-only key handler.
 *
 * Real radio inputs give arrow-key navigation, correct announcement as a group,
 * and roving focus without any of that being written by hand.
 *
 * An option may carry a `short` label. Only the drawn text changes: the word
 * stays in the accessible name, so shrinking a control to initials on a phone
 * does not turn "Series" into "S" for anyone listening to it.
 */
export default function SegmentedControl({ name, value, onChange, options, label, className }) {
  return (
    <fieldset className={cx('ui-segmented', className)}>
      <legend className="sr-only">{label}</legend>
      {options.map((opt) => (
        <label
          key={opt.value}
          className={cx('ui-segmented__option', value === opt.value && 'is-selected')}
        >
          <input
            type="radio"
            className="sr-only"
            name={name}
            value={opt.value}
            checked={value === opt.value}
            onChange={() => onChange(opt.value)}
          />
          {/* `short` is for when the control has to give up width — the
              initial is what is drawn, the word is what is announced. */}
          <span aria-hidden="true">{opt.short ?? opt.label}</span>
          <span className="sr-only">{opt.label}</span>
        </label>
      ))}
    </fieldset>
  )
}

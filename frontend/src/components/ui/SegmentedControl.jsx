import { cx } from '../../utils/cx'

/**
 * The Name / Series switch, previously copy-pasted between SearchBar and
 * CustomsPage as `<span role="button">` pairs with an Enter-only key handler.
 *
 * Real radio inputs give arrow-key navigation, correct announcement as a group,
 * and roving focus without any of that being written by hand.
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
          <span>{opt.label}</span>
        </label>
      ))}
    </fieldset>
  )
}

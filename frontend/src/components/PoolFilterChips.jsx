import { Button } from './ui'

/**
 * The four pool facets, in catalog order. `waifu`/`husbando` are the two
 * genders and `anime`/`game` the two roulette pools; the facets are additive,
 * so more than one can be on.
 */
export const POOL_FILTERS = [
  { key: 'waifu', label: 'Waifu' },
  { key: 'husbando', label: 'Husbando' },
  { key: 'anime', label: 'Anime' },
  { key: 'game', label: 'Game' },
]

/**
 * The Add form's suggestion filter and the character editor's trait editor are
 * the same four toggles under the same legend, so they share one control. What
 * a caller does with the selection is its own business: the Add form narrows
 * name suggestions with it, the editor writes it to the character.
 */
export function PoolFilterChips({ value = [], onToggle }) {
  return (
    <fieldset className="pool-filter">
      <legend className="pool-filter__legend">Gender And Roulette Pools (Optional)</legend>
      <div className="pool-filter__options">
        {POOL_FILTERS.map(({ key, label }) => (
          <Button
            key={key}
            variant="secondary"
            size="sm"
            aria-pressed={value.includes(key)}
            onClick={() => onToggle(key)}
          >
            {label}
          </Button>
        ))}
      </div>
    </fieldset>
  )
}

import { useCallback, useState } from 'react'
import { apiClient } from '../api'
import { pickPixel } from '../utils/imagePick'

/**
 * The staff accent picker.
 *
 * Split out of `CharacterPage`. Arming it turns the portrait and gallery into a
 * pixel sampler; the server samples the image (keyed by row id, never a caller
 * URL), so a click only has to carry the point within the image. Setting a
 * manual colour or clearing it back to the measured one are the same request.
 */
export function useAccentOverride({ name, addToast, onChanged }) {
  const [pick, setPick] = useState(false)
  const [busy, setBusy] = useState(false)

  const apply = useCallback(
    async (payload) => {
      setBusy(true)
      try {
        const res = await apiClient.setAccentOverride({ name, ...payload })
        addToast(res.manual ? 'Accent colour saved' : 'Accent reset to measured', 'success')
        setPick(false)
        await onChanged(res)
      } catch (err) {
        addToast(err.message, 'error')
      } finally {
        setBusy(false)
      }
    },
    [name, addToast, onChanged],
  )

  const pickFromGallery = useCallback(
    (row, point) => {
      if (!row.thumb) {
        addToast('That image has no thumbnail to sample', 'error')
        return
      }
      apply({ image_id: row.id, u: point.u, v: point.v })
    },
    [apply, addToast],
  )

  const pickFromPortrait = useCallback(
    (event) => {
      const img = event.currentTarget.querySelector('img')
      const point = pickPixel(img, event.clientX, event.clientY)
      apply({ portrait: true, u: point.u, v: point.v })
    },
    [apply],
  )

  const clear = useCallback(() => apply({ clear: true }), [apply])

  return {
    pick,
    busy,
    togglePick: useCallback(() => setPick((on) => !on), []),
    pickFromGallery,
    pickFromPortrait,
    clear,
  }
}

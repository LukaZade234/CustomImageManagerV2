/**
 * Moving a selection of gallery images to a new position.
 *
 * Pure array maths, deliberately separate from the drag machinery that drives
 * it: the ordering rules are what actually matter to a user and they are far
 * easier to reason about — and to test — without pointer events in the way.
 */

/**
 * Nudge a drop target off the selection itself.
 *
 * Dropping onto an image you are already dragging has no meaning, so the target
 * moves to the nearest index that is not part of the selection: forwards first,
 * then backwards.
 */
export function adjustDropTarget(toIndex, pickedSet, len) {
  if (len <= 0) return 0
  let t = toIndex
  if (t < 0) t = 0
  if (t >= len) t = len - 1
  if (!pickedSet.has(t)) return t
  for (let i = t + 1; i < len; i++) if (!pickedSet.has(i)) return i
  for (let i = t - 1; i >= 0; i--) if (!pickedSet.has(i)) return i
  return 0
}

/**
 * Move the images at `fromIndices` to sit **immediately before** whatever is
 * currently at `toIndex`, keeping the selection's own order.
 *
 * That is the rule the drag interaction implies — you drop *onto* an image and
 * the selection lands in front of it — but it was never written down, and
 * "insert before the target" and "end up at that index" give different answers.
 * Moving ['a'] from 0 to 2 in [a,b,c,d,e] yields [b,a,c,d,e], not [b,c,a,d,e]:
 * 'a' sits before 'c', which was the drop target.
 */
export function moveGroupInArray(arr, fromIndices, toIndex) {
  const sorted = [...fromIndices].sort((a, b) => a - b)
  const pickedSet = new Set(sorted)
  const picked = sorted.map((i) => arr[i])
  let t = toIndex
  if (pickedSet.has(t)) {
    t = adjustDropTarget(t, pickedSet, arr.length)
  }
  if (t < 0) t = 0
  const without = arr.filter((_, i) => !pickedSet.has(i))
  let insertBefore = 0
  for (let i = 0; i < t && i < arr.length; i++) {
    if (!pickedSet.has(i)) insertBefore++
  }
  return [...without.slice(0, insertBefore), ...picked, ...without.slice(insertBefore)]
}

/** Whether two orderings are the same, so a no-op reorder can skip the request. */
export function ordersEqual(a, b) {
  if (a.length !== b.length) return false
  return a.every((u, i) => u === b[i])
}

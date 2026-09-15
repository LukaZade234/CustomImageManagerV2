/**
 * The moderation verbs, and how each one reads.
 *
 * `tone` picks a status colour for the badge and the message title: a warning is
 * the caution amber, a suspension its own orange, a ban the refuse red. The
 * inbox and the moderation history both render from this map, so the vocabulary
 * lives in one place and a new verb cannot choose a colour of its own.
 *
 * Only `warn` is sent today; the other two are here so the colour ramp is defined
 * once, when they land.
 */
export const MODERATION_ACTIONS = {
  warn: { label: 'Warning', tone: 'warning' },
  suspend: { label: 'Suspension', tone: 'caution' },
  ban: { label: 'Ban', tone: 'danger' },
}

/** The label and tone for an action, or null if it is not a moderation action. */
export function moderationAction(action) {
  return MODERATION_ACTIONS[action] ?? null
}

/**
 * The same, for the account state rather than the verb that set it: the stored
 * status is `suspended` / `banned`, the action is `suspend` / `ban`.
 */
export function moderationStatus(status) {
  if (status === 'banned') return MODERATION_ACTIONS.ban
  if (status === 'suspended') return MODERATION_ACTIONS.suspend
  return null
}

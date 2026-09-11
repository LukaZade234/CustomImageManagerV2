import { useEffect, useState } from 'react'
import { apiClient } from '../../api'
import { Button, Card } from '../../components/ui'
import { signInUrl } from '../../config'
import { useStore } from '../../store/useStore'

/**
 * Account and preferences.
 *
 * General settings live here rather than in a tab of their own: there are four
 * of them, and a tab holding four switches is a tab you have to explain.
 */

const THEMES = [
  { value: 'system', label: 'Follow system' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

/** A labelled switch. `hint` carries the consequence, which is the part that matters. */
function Toggle({ id, checked, onChange, disabled, label, hint }) {
  return (
    <div className="profile-toggle">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        disabled={disabled}
        onChange={(e) => onChange(e.target.checked)}
      />
      <label htmlFor={id}>
        <span className="profile-toggle__label">{label}</span>
        <span className="profile-toggle__hint">{hint}</span>
      </label>
    </div>
  )
}

export default function SettingsTab() {
  const me = useStore((s) => s.me)
  const loadMe = useStore((s) => s.loadMe)
  const theme = useStore((s) => s.theme)
  const setTheme = useStore((s) => s.setTheme)
  const addToast = useStore((s) => s.addToast)

  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (me?.settings) setSettings(me.settings)
  }, [me])

  const save = async (change) => {
    // Optimistic: a switch that waits for a round trip feels broken, and the
    // failure path puts it straight back.
    const before = settings
    setSettings({ ...settings, ...change })
    setSaving(true)
    try {
      const result = await apiClient.updateSettings(change)
      setSettings(result.settings)
    } catch (e) {
      setSettings(before)
      addToast(e.message || 'Could not save that setting', 'error')
    } finally {
      setSaving(false)
    }
  }

  const signedIn = Boolean(me?.signed_in)
  const busy = !settings || saving

  return (
    <>
      <Card as="section" padding="lg">
        <h2 className="section-heading">Account</h2>
        <div className="profile-identity">
          <p className="text-meta profile-lead">
            {signedIn
              ? 'Your uploads and lists are tied to your Discord account.'
              : 'Everything works without an account. Signing in only makes it durable.'}
          </p>
          {signedIn ? (
            <Button
              variant="secondary"
              onClick={async () => {
                await apiClient.logout()
                await loadMe()
                addToast('Signed out of this browser', 'info')
              }}
            >
              Sign out
            </Button>
          ) : (
            me?.discord_available && (
              <Button as="a" href={signInUrl('/profile')}>
                Sign in with Discord
              </Button>
            )
          )}
        </div>
        {!signedIn && (
          <p className="profile-warning text-meta">
            This profile lives in a cookie. Clear your cookies, or open the site in another browser,
            and the name above, your saved list and everything you have uploaded stop being yours.
            Signing in with Discord ties them to an account instead — it asks for nothing but your
            username.
          </p>
        )}
      </Card>

      <Card as="section" padding="lg">
        <h2 className="section-heading">Appearance</h2>
        <fieldset className="profile-themes">
          <legend className="sr-only">Theme</legend>
          {THEMES.map((option) => (
            <label key={option.value} className="profile-theme">
              <input
                type="radio"
                name="theme"
                value={option.value}
                checked={theme === option.value}
                onChange={() => setTheme(option.value)}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </fieldset>
      </Card>

      <Card as="section" padding="lg">
        <h2 className="section-heading">Content</h2>
        <Toggle
          id="show-nsfw"
          checked={Boolean(settings?.show_nsfw)}
          disabled={busy}
          onChange={(v) => save({ show_nsfw: v })}
          label="Show images marked NSFW"
          hint="Nothing is marked yet, so this changes nothing today. It is recorded now so your choice already applies on the day the filter arrives."
        />
      </Card>

      <Card as="section" padding="lg">
        <h2 className="section-heading">Privacy</h2>
        <p className="text-meta profile-lead">
          Both of these change what other people see. Neither changes what is stored: your uploads
          stay yours, so you can always remove them, and turning a switch back off brings your name
          back everywhere it appeared. Moderators can still see who added an image — they need it to
          moderate.
        </p>
        <Toggle
          id="hide-attribution"
          checked={Boolean(settings?.hide_attribution)}
          disabled={busy}
          onChange={(v) => save({ hide_attribution: v })}
          label="Do not show my name on images I add"
          hint="Others see the image as having no owner. You still see your own name."
        />
        <Toggle
          id="hide-leaderboard"
          checked={Boolean(settings?.hide_from_leaderboard)}
          disabled={busy}
          onChange={(v) => save({ hide_from_leaderboard: v })}
          label="Keep me off the contributor ranking"
          hint="Removes you from the home page list. Your images still count toward the totals."
        />
        {!signedIn && (
          <p className="text-micro profile-note">
            The ranking only ever lists people signed in with Discord, so it does not include you
            yet either way.
          </p>
        )}
      </Card>
    </>
  )
}

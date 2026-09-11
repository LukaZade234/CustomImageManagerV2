import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient, getImageUrl } from '../api'
import { Button, Card, EmptyState } from '../components/ui'
import { apiUrl, signInUrl } from '../config'
import { useStore } from '../store/useStore'

/**
 * Your account, your preferences, and the two lists nothing else can reach.
 *
 * Hidden and removed images were previously only reachable from the character
 * page holding them, so anyone who hid or removed something and did not recall
 * where had no way back to it. That dead end is the strongest reason this page
 * exists; the settings are the second.
 */

const THEMES = [
  { value: 'system', label: 'Follow system' },
  { value: 'light', label: 'Light' },
  { value: 'dark', label: 'Dark' },
]

/** A labelled switch. `hint` carries the consequence, which is the part people need. */
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

function ImageList({ items, emptyTitle, emptyBody, action, onAction, busyId }) {
  if (items === null) return <p className="text-meta">Loading…</p>
  if (items.length === 0) return <EmptyState title={emptyTitle} description={emptyBody} />

  return (
    <ul className="profile-images">
      {items.map((row) => (
        <li key={row.id} className="profile-images__item">
          <Link to={`/character/${encodeURIComponent(row.character)}`}>
            <img
              className="profile-images__thumb"
              src={row.thumb ? apiUrl(row.thumb) : getImageUrl(row.url)}
              alt=""
              loading="lazy"
              decoding="async"
            />
          </Link>
          <div className="profile-images__text">
            <Link
              className="profile-images__name"
              to={`/character/${encodeURIComponent(row.character)}`}
            >
              {row.character}
            </Link>
            {row.removed_reason && <span className="text-micro">{row.removed_reason}</span>}
          </div>
          <Button size="sm" disabled={busyId === row.id} onClick={() => onAction(row)}>
            {busyId === row.id ? '…' : action}
          </Button>
        </li>
      ))}
    </ul>
  )
}

export default function ProfilePage() {
  const me = useStore((s) => s.me)
  const loadMe = useStore((s) => s.loadMe)
  const theme = useStore((s) => s.theme)
  const setTheme = useStore((s) => s.setTheme)
  const addToast = useStore((s) => s.addToast)

  const [settings, setSettings] = useState(null)
  const [saving, setSaving] = useState(false)
  const [hidden, setHidden] = useState(null)
  const [removed, setRemoved] = useState(null)
  const [busyId, setBusyId] = useState(null)

  useEffect(() => {
    loadMe()
  }, [loadMe])

  useEffect(() => {
    if (me?.settings) setSettings(me.settings)
  }, [me])

  const reload = useCallback(async () => {
    const [h, r] = await Promise.all([
      apiClient.getMyHidden().catch(() => []),
      apiClient.getMyRemoved().catch(() => []),
    ])
    setHidden(h)
    setRemoved(r)
  }, [])

  useEffect(() => {
    reload()
  }, [reload])

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

  const unhide = async (row) => {
    setBusyId(row.id)
    try {
      await apiClient.unhideImages([row.id])
      setHidden((list) => list.filter((h) => h.id !== row.id))
      addToast('Image is visible to you again', 'success')
    } catch (e) {
      addToast(e.message || 'Could not unhide that image', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const restore = async (row) => {
    setBusyId(row.id)
    try {
      // Restore is addressed by character and URL, not by image id.
      await apiClient.restoreImages(row.character, [row.url])
      setRemoved((list) => list.filter((r) => r.id !== row.id))
      addToast(`Restored to ${row.character}`, 'success')
    } catch (e) {
      addToast(e.message || 'Could not restore that image', 'error')
    } finally {
      setBusyId(null)
    }
  }

  const signedIn = Boolean(me?.signed_in)

  return (
    <div className="profile">
      <Card as="section" padding="lg">
        <h1 className="page-title">Profile</h1>
        <div className="profile-identity">
          <div>
            <p className="profile-identity__handle">{me?.handle ?? '…'}</p>
            <p className="text-meta">
              {signedIn
                ? 'Signed in with Discord.'
                : 'A name your browser was given. No account needed.'}
              {me?.is_moderator && ` Role: ${me.role}.`}
            </p>
          </div>
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
            and the name above, your hidden list and everything you have uploaded stop being yours.
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
          disabled={!settings || saving}
          onChange={(v) => save({ hide_attribution: v })}
          label="Do not show my name on images I add"
          hint="Others see the image as having no owner. You still see your own name."
        />
        <Toggle
          id="hide-leaderboard"
          checked={Boolean(settings?.hide_from_leaderboard)}
          disabled={!settings || saving}
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

      <Card as="section" padding="lg">
        <h2 className="section-heading">Hidden images</h2>
        <p className="text-meta profile-lead">
          Hidden only for you — nobody else is affected, and the image is not removed.
        </p>
        <ImageList
          items={hidden}
          emptyTitle="Nothing hidden"
          emptyBody="Images you hide from a character page will collect here."
          action="Unhide"
          onAction={unhide}
          busyId={busyId}
        />
      </Card>

      <Card as="section" padding="lg">
        <h2 className="section-heading">Removed images</h2>
        <p className="text-meta profile-lead">
          Nothing is ever deleted from the image host, so anything here can be put back.
        </p>
        <ImageList
          items={removed}
          emptyTitle="Nothing removed"
          emptyBody="Images you remove stay here in case you change your mind."
          action="Restore"
          onAction={restore}
          busyId={busyId}
        />
      </Card>
    </div>
  )
}

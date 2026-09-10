import { Link, useLocation } from 'react-router-dom'
import { signInUrl } from '../config'
import { useStore } from '../store/useStore'
import SearchBar from './SearchBar'
import { Button, IconButton } from './ui'

/** Announces the current state, since the button cycles rather than toggles. */
const THEME_LABELS = {
  system: 'Theme: following system. Switch to light.',
  light: 'Theme: light. Switch to dark.',
  dark: 'Theme: dark. Switch to system.',
}

export default function Navbar() {
  const theme = useStore((s) => s.theme)
  const cycleTheme = useStore((s) => s.cycleTheme)
  const me = useStore((s) => s.me)
  const signOut = useStore((s) => s.signOut)
  const location = useLocation()
  const here = `${location.pathname}${location.search}`

  return (
    <nav className="navbar">
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand">
          <svg
            aria-hidden="true"
            width="24"
            height="24"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
            <polyline points="9 22 9 12 15 12 15 22" />
          </svg>
          <span>ImgManager</span>
        </Link>
        <div className="navbar-center search-container">
          <SearchBar />
        </div>
        <div className="navbar-right">
          <Button as={Link} to="/add" variant="primary" className="btn-nav">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            <span>Add Character</span>
          </Button>
          <Button as={Link} to="/customs" variant="ghost" className="btn-nav">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden
            >
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
              <circle cx="8.5" cy="8.5" r="1.5" />
              <polyline points="21 15 16 10 5 21" />
            </svg>
            <span>Customs</span>
          </Button>
          <Button as={Link} to="/saved" variant="ghost" className="btn-nav">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              aria-hidden
            >
              <path d="M19 21l-7-5-7 5V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2z" />
            </svg>
            <span>Saved</span>
          </Button>
          {me?.handle &&
            (me.signed_in ? (
              <button
                type="button"
                className="navbar-handle navbar-handle--signed-in text-meta"
                onClick={signOut}
                title={`Signed in as ${me.handle}. Click to sign out of this browser — your uploads stay yours.`}
              >
                {me.handle}
                {me.is_moderator && <span className="navbar-role">{me.role}</span>}
              </button>
            ) : (
              <span
                className="navbar-handle text-meta"
                title={`You appear to others as "${me.handle}". No sign-in needed; this follows your browser.`}
              >
                {me.handle}
              </span>
            ))}
          {me?.discord_available && !me.signed_in && (
            <a
              className="ui-btn ui-btn--secondary ui-btn--md btn-nav navbar-signin"
              href={signInUrl(here)}
              title="Optional. Keeps your uploads yours if you clear cookies or switch browser."
            >
              <svg
                aria-hidden="true"
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="currentColor"
              >
                <path d="M19.5 5.4A17 17 0 0 0 15.3 4l-.3.5a15.7 15.7 0 0 1 3.7 1.3 12.4 12.4 0 0 0-9.5 0A15.7 15.7 0 0 1 13 4.5L12.7 4A17 17 0 0 0 8.5 5.4C5.8 9.3 5.1 13.1 5.4 16.8A17 17 0 0 0 10.6 20l.9-1.3a11 11 0 0 1-1.7-.8l.4-.3a12 12 0 0 0 9.6 0l.4.3a11 11 0 0 1-1.7.8l.9 1.3a17 17 0 0 0 5.2-3.2c.4-4.3-.7-8-2.6-11.4ZM10.3 14.6c-1 0-1.9-.9-1.9-2.1s.8-2.1 1.9-2.1 1.9 1 1.9 2.1-.8 2.1-1.9 2.1Zm5.4 0c-1 0-1.9-.9-1.9-2.1s.8-2.1 1.9-2.1 1.9 1 1.9 2.1-.8 2.1-1.9 2.1Z" />
              </svg>
              <span>Sign in</span>
            </a>
          )}
          <IconButton className="theme-toggle-btn" label={THEME_LABELS[theme]} onClick={cycleTheme}>
            {theme === 'dark' ? (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" />
              </svg>
            ) : theme === 'light' ? (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
            ) : (
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden
              >
                <rect x="2" y="4" width="20" height="13" rx="2" />
                <line x1="8" y1="21" x2="16" y2="21" />
                <line x1="12" y1="17" x2="12" y2="21" />
              </svg>
            )}
          </IconButton>
        </div>
      </div>
    </nav>
  )
}

import { useEffect, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useMediaQuery } from '../hooks/useMediaQuery'
import { useStore } from '../store/useStore'
import SearchBar from './SearchBar'
import { Button } from './ui'

/** Below this the bar folds: the wordmark goes, the links go behind a button. */
const COMPACT = '(max-width: 960px)'

export default function Navbar() {
  const me = useStore((s) => s.me)
  const compact = useMediaQuery(COMPACT)
  const [menuOpen, setMenuOpen] = useState(false)
  const location = useLocation()

  // Following a link is the end of the menu's purpose. The path is the trigger
  // rather than a value the effect reads, which the rule cannot tell apart.
  // biome-ignore lint/correctness/useExhaustiveDependencies: closing on navigation is the point
  useEffect(() => setMenuOpen(false), [location.pathname])
  // Widening the window brings the links back on their own; leaving the flag
  // set would reopen the menu the next time it narrowed.
  useEffect(() => {
    if (!compact) setMenuOpen(false)
  }, [compact])

  /**
   * The links are the same links either way.
   *
   * On a phone the bar was three rows deep — wordmark and four controls, then
   * the search field, then the sort — and the first two were mostly whitespace
   * around icons. Folding them behind one button puts everything on one line
   * and gives the width to the search field, which is what the bar is for.
   */
  const linksVisible = !compact || menuOpen

  return (
    <nav
      className="navbar"
      onKeyDown={(event) => {
        if (event.key === 'Escape') setMenuOpen(false)
      }}
    >
      <div className="navbar-inner">
        <Link to="/" className="navbar-brand" aria-label="ImgManager home">
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
          {/* The name is the one thing here that is decoration rather than a
              destination, so it is the first thing to go when space is short.
              Dropped rather than hidden, so there is one answer to whether it
              is there and both the layout and a screen reader read the same
              one. */}
          {!compact && <span className="navbar-brand__name">ImgManager</span>}
        </Link>
        {/* Reaching for the search field is a statement that you are done with
            the menu, and the menu is standing in its way. */}
        <div className="navbar-center search-container" onFocusCapture={() => setMenuOpen(false)}>
          <SearchBar compact={compact} minimal={compact && menuOpen} />
        </div>
        {linksVisible && (
          <div className="navbar-right" id="navbar-links">
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
            <Button as={Link} to="/profile/saved" variant="ghost" className="btn-nav">
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
            {/*
              One destination instead of three controls. The handle, the sign-in
              link and the theme toggle all lived here; sign-in and theme are
              settings, and settings needed a home the moment there was more than
              one of them. The handle stays visible next to the icon so signing in
              still reads as an upgrade rather than something hidden behind a
              glyph.
            */}
            <Link
              className="ui-btn ui-btn--secondary ui-btn--md btn-nav navbar-profile"
              to="/profile"
              title={
                me?.signed_in
                  ? `Signed in as ${me.handle}. Profile and settings.`
                  : `You appear to others as "${me?.handle ?? '…'}". Profile and settings.`
              }
            >
              <svg
                aria-hidden="true"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
                <circle cx="12" cy="7" r="4" />
              </svg>
              <span className="navbar-profile__name">{me?.handle ?? 'Profile'}</span>
              {me?.is_moderator && <span className="navbar-role">{me.role}</span>}
            </Link>
          </div>
        )}
        {/* Last, because the links it unfolds appear to its left and because a
            thumb reaches the end of the bar more easily than the middle. */}
        {compact && (
          <button
            type="button"
            className="ui-btn ui-btn--ghost ui-btn--md btn-nav navbar-menu-toggle"
            aria-expanded={menuOpen}
            aria-controls="navbar-links"
            aria-label={menuOpen ? 'Hide menu' : 'Show menu'}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <svg
              aria-hidden="true"
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
            >
              <line x1="3" y1="6" x2="21" y2="6" />
              <line x1="3" y1="12" x2="21" y2="12" />
              <line x1="3" y1="18" x2="21" y2="18" />
            </svg>
          </button>
        )}
      </div>
    </nav>
  )
}

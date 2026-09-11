import { Link } from 'react-router-dom'
import { useStore } from '../store/useStore'
import SearchBar from './SearchBar'
import { Button } from './ui'

export default function Navbar() {
  const me = useStore((s) => s.me)

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
      </div>
    </nav>
  )
}

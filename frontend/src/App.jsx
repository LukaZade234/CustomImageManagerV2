import React, { lazy, Suspense } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import RequireModerator from './components/RequireModerator'
import RestrictionBanner from './components/RestrictionBanner'
import Toast from './components/Toast'
import { Button, Card } from './components/ui'
import HomePage from './pages/HomePage'

// Everything past the landing page is loaded on demand. The site is one bundle
// otherwise, so every anonymous visitor used to download the moderation console,
// the Mudae import panel and the profile subtree they cannot open. HomePage and
// the shared chrome stay eager: the landing page is the most common entry and
// delaying it would add a round trip at the worst moment.
const AddPage = lazy(() => import('./pages/AddPage'))
const CharacterPage = lazy(() => import('./pages/CharacterPage'))
const CustomsPage = lazy(() => import('./pages/CustomsPage'))
const NotificationsPage = lazy(() => import('./pages/NotificationsPage'))
const SearchResultsPage = lazy(() => import('./pages/SearchResultsPage'))
const ProfileLayout = lazy(() => import('./pages/profile/ProfileLayout'))
const HiddenTab = lazy(() => import('./pages/profile/HiddenTab'))
const HistoryTab = lazy(() => import('./pages/profile/HistoryTab'))
const RemovedTab = lazy(() => import('./pages/profile/RemovedTab'))
const SavedTab = lazy(() => import('./pages/profile/SavedTab'))
const SettingsTab = lazy(() => import('./pages/profile/SettingsTab'))
const DuplicatesPage = lazy(() => import('./pages/moderation/DuplicatesPage'))
const ModerationLayout = lazy(() => import('./pages/moderation/ModerationLayout'))
const ModerationPage = lazy(() => import('./pages/moderation/ModerationPage'))
const ReportsPage = lazy(() => import('./pages/moderation/ReportsPage'))

/** Prevents a blank screen if a child throws (e.g. browser API quirks). */
class AppErrorBoundary extends React.Component {
  constructor(props) {
    super(props)
    this.state = { err: null }
  }

  static getDerivedStateFromError(err) {
    return { err }
  }

  render() {
    if (this.state.err) {
      const msg = this.state.err?.message || String(this.state.err)
      return (
        <main className="container">
          <Card padding="lg">
            <h1 className="page-title">Something went wrong</h1>
            <p className="text-body error-boundary__message">{msg}</p>
            <Button variant="primary" onClick={() => window.location.reload()}>
              Reload page
            </Button>
          </Card>
        </main>
      )
    }
    return this.props.children
  }
}

function App() {
  return (
    <>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <Navbar />
      <Toast />
      <AppErrorBoundary>
        <RestrictionBanner />
        <main id="main-content" className="container" tabIndex={-1}>
          {/*
            One boundary around the route tree. The fallback is deliberately near
            empty -- pages own their own skeletons, and a second loading design
            here would only add a flash and a layout shift -- but it still tells a
            screen reader something is happening. The error boundary stays above
            it, so a chunk that fails to load lands on "Something went wrong"
            rather than a blank page.
          */}
          <Suspense
            fallback={
              <div className="route-fallback" role="status" aria-live="polite">
                <span className="sr-only">Loading…</span>
              </div>
            }
          >
            <Routes>
              <Route path="/" element={<HomePage />} />
              <Route path="/saved" element={<Navigate to="/profile/saved" replace />} />
              <Route path="/add" element={<AddPage />} />
              <Route path="/customs" element={<CustomsPage />} />
              <Route path="/profile" element={<ProfileLayout />}>
                <Route index element={<SettingsTab />} />
                <Route path="saved" element={<SavedTab />} />
                <Route path="history" element={<HistoryTab />} />
                <Route path="hidden" element={<HiddenTab />} />
                <Route path="removed" element={<RemovedTab />} />
                <Route
                  path="moderation"
                  element={
                    // Eager, and outside the moderation chunk: a non-moderator is
                    // redirected without the console ever being downloaded.
                    <RequireModerator>
                      <ModerationLayout />
                    </RequireModerator>
                  }
                >
                  <Route index element={<ModerationPage />} />
                  <Route path="reports" element={<ReportsPage />} />
                  <Route path="duplicates" element={<DuplicatesPage />} />
                </Route>
              </Route>
              <Route path="/search" element={<SearchResultsPage />} />
              <Route path="/notifications" element={<NotificationsPage />} />
              {/* The old top-level route, kept as a redirect for existing links. */}
              <Route path="/moderation" element={<Navigate to="/profile/moderation" replace />} />
              <Route path="/character/:name" element={<CharacterPage />} />
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </Suspense>
        </main>
      </AppErrorBoundary>
    </>
  )
}

export default App

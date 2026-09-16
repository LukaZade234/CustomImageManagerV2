import React from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import RequireModerator from './components/RequireModerator'
import RestrictionBanner from './components/RestrictionBanner'
import Toast from './components/Toast'
import { Button, Card } from './components/ui'
import AddPage from './pages/AddPage'
import CharacterPage from './pages/CharacterPage'
import CustomsPage from './pages/CustomsPage'
import HomePage from './pages/HomePage'
import DuplicatesPage from './pages/moderation/DuplicatesPage'
import ModerationPage from './pages/moderation/ModerationPage'
import NotificationsPage from './pages/NotificationsPage'
import HiddenTab from './pages/profile/HiddenTab'
import HistoryTab from './pages/profile/HistoryTab'
import ProfileLayout from './pages/profile/ProfileLayout'
import RemovedTab from './pages/profile/RemovedTab'
import SavedTab from './pages/profile/SavedTab'
import SettingsTab from './pages/profile/SettingsTab'
import SearchResultsPage from './pages/SearchResultsPage'

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
                  <RequireModerator>
                    <ModerationPage />
                  </RequireModerator>
                }
              />
              <Route
                path="moderation/duplicates"
                element={
                  <RequireModerator>
                    <DuplicatesPage />
                  </RequireModerator>
                }
              />
            </Route>
            <Route path="/search" element={<SearchResultsPage />} />
            <Route path="/notifications" element={<NotificationsPage />} />
            {/* The old top-level route, kept as a redirect for existing links. */}
            <Route path="/moderation" element={<Navigate to="/profile/moderation" replace />} />
            <Route path="/character/:name" element={<CharacterPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </AppErrorBoundary>
    </>
  )
}

export default App

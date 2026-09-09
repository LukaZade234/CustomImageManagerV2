import React, { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import Toast from './components/Toast'
import AddPage from './pages/AddPage'
import CharacterPage from './pages/CharacterPage'
import CustomsPage from './pages/CustomsPage'
import HomePage from './pages/HomePage'
import SavedPage from './pages/SavedPage'
import SearchResultsPage from './pages/SearchResultsPage'
import { useStore } from './store/useStore'

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
        <main className="container" style={{ paddingTop: 24 }}>
          <div className="home-page" style={{ padding: 24 }}>
            <h1 className="page-title">Something went wrong</h1>
            <p className="text-body" style={{ marginBottom: 16 }}>
              {msg}
            </p>
            <button
              type="button"
              className="action-btn primary"
              onClick={() => window.location.reload()}
            >
              Reload page
            </button>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}

function App() {
  const loadCharacters = useStore((s) => s.loadCharacters)
  const loadSaved = useStore((s) => s.loadSaved)

  useEffect(() => {
    loadCharacters()
    loadSaved()
  }, [loadCharacters, loadSaved])

  return (
    <>
      <Navbar />
      <Toast />
      <AppErrorBoundary>
        <main className="container">
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/saved" element={<SavedPage />} />
            <Route path="/add" element={<AddPage />} />
            <Route path="/customs" element={<CustomsPage />} />
            <Route path="/search" element={<SearchResultsPage />} />
            <Route path="/character/:name" element={<CharacterPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </AppErrorBoundary>
    </>
  )
}

export default App

import React, { useEffect } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'
import Navbar from './components/Navbar'
import Toast from './components/Toast'
import { Button, Card } from './components/ui'
import AddPage from './pages/AddPage'
import CharacterPage from './pages/CharacterPage'
import CustomsPage from './pages/CustomsPage'
import HomePage from './pages/HomePage'
import ProfilePage from './pages/ProfilePage'
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
  const loadCharacters = useStore((s) => s.loadCharacters)
  const loadSaved = useStore((s) => s.loadSaved)
  const loadMe = useStore((s) => s.loadMe)

  useEffect(() => {
    loadCharacters()
    loadSaved()
    loadMe()
  }, [loadCharacters, loadSaved, loadMe])

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
            <Route path="/profile" element={<ProfilePage />} />
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

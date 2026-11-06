// Claimwise app shell: public pages, Agent Dossier and Mock Console.
import { useEffect, useState } from 'react'
import HistorySidebar from './components/HistorySidebar.jsx'
import LandingPage from './components/LandingPage.jsx'
import { buildView } from './flow.js'
import Dossier from './layouts/Dossier.jsx'
import MockConsole from './mocks/MockConsole.jsx'
import { scrollToTop, useSmoothScroll } from './motion.js'
import { useClaimwise } from './useClaimwise.js'

const USER_STORAGE_KEY = 'claimwise_user_v1'
const GUEST_PROFILE = { name: 'Guest' }

/** Read stored user profile from localStorage. */
function readStoredUser() {
  if (typeof window === 'undefined') return null
  try {
    const raw = window.localStorage.getItem(USER_STORAGE_KEY)
    return raw ? JSON.parse(raw) : null
  } catch {
    return null
  }
}

/** Clear any profile left from an earlier workspace visit. */
function clearStoredUser() {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(USER_STORAGE_KEY)
  } catch {
    // Ignore storage quota errors
  }
}

/** Read the active workspace, mock console or public page from the browser URL. */
function resolveModeFromUrl() {
  if (typeof window === 'undefined') return 'landing'
  const path = window.location.pathname.replace(/\/$/, '')
  const page = path.slice(1)
  if (page === 'policy' || page === 'privacy' || page === 'terms') return page
  const params = new URLSearchParams(window.location.search)
  const view = params.get('view')
  if (path === '/mocks' || view === 'mocks' || window.location.hash === '#mocks') return 'mocks'
  if (path === '/app' || view === 'dossier') return 'dossier'
  if (view === 'home' || window.location.hash === '#home') return 'landing'
  return 'landing'
}

/** Render the public site, Agent Dossier or Mock Console with the claim state kept mounted. */
export default function App() {
  const cw = useClaimwise()
  const [user, setUser] = useState(() => readStoredUser() ?? GUEST_PROFILE)
  const [mode, setMode] = useState(resolveModeFromUrl)
  useSmoothScroll()

  useEffect(() => {
    function onPopState() {
      setMode(resolveModeFromUrl())
    }
    window.addEventListener('popstate', onPopState)
    return () => window.removeEventListener('popstate', onPopState)
  }, [])

  function switchMode(next) {
    setMode(next)
    if (typeof window !== 'undefined') {
      const targetPath = next === 'mocks' ? '/mocks' : next === 'dossier' ? '/app' : '/'
      window.history.pushState({}, '', targetPath)
      scrollToTop()
    }
  }

  function handleSignOut() {
    setUser(GUEST_PROFILE)
    clearStoredUser()
    switchMode('landing')
  }

  if (mode === 'mocks') {
    return <MockConsole onBackToApp={() => switchMode('landing')} />
  }

  if (mode !== 'dossier') {
    return (
      <LandingPage
        page={mode}
        onEnter={() => switchMode('dossier')}
        onOpenMocks={() => switchMode('mocks')}
      />
    )
  }

  return (
    <>
      <HistorySidebar
        cw={cw}
        user={user}
        onGoHome={() => switchMode('landing')}
        onSignOut={handleSignOut}
      />
      <Dossier cw={cw} view={buildView(cw)} />
    </>
  )
}

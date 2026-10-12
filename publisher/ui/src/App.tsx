import { lazy, Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { api, clearPasscode, onUnauthorized, restoreSession } from './api/client'
import { PasscodeView } from './views/PasscodeView'
import { DashboardView } from './views/DashboardView'
import { LibraryView } from './views/library/LibraryView'
import { EpisodeDetailView } from './views/library/EpisodeDetailView'
import { ScheduleView } from './views/schedule/ScheduleView'
import { ActivityView } from './views/ActivityView'
import { SettingsView } from './views/SettingsView'
import { MakeBatchView } from './views/MakeBatchView'
import { StudioView } from './views/studio/StudioView'
import { NewFormatView } from './views/studio/NewFormatView'
import { StoryJobsView } from './views/studio/StoryJobsView'
import { StoryJobView } from './views/studio/StoryJobView'
import { StoryRendersView } from './views/studio/StoryRendersView'
import { StorySettingsView } from './views/studio/StorySettingsView'
import { Loading } from './components/Loading'

// Remotion (preview and export) loads only on this screen.
const ExportView = lazy(() => import('./views/studio/ExportView'))
import { GuideView } from './views/GuideView'
import { AppNav } from './components/AppNav'
import { StepLine } from './components/StepLine'
import { JourneyContext, useJourneyLoader } from './hooks/useJourney'
import { shortHash } from './lib/format'
import { helpAnchor } from './lib/help'
import { screenStep } from './lib/journey'
import { guideHash, routeFromHash, SCREEN_TITLES, screenOf, type Route } from './views'

function scrollToSection(section: string | undefined) {
  if (!section) return
  let expected: number | null = null
  const go = () => {
    // Stop following the section once the owner has scrolled themselves.
    if (expected !== null && Math.abs(window.scrollY - expected) > 2) return
    const el = document.getElementById(section)
    if (!el || typeof el.scrollIntoView !== 'function') return
    el.scrollIntoView({ block: 'start' })
    expected = window.scrollY
  }
  // Sections above it load their data after the first paint and push it down: settle a few times.
  for (const ms of [0, 300, 800, 1600]) window.setTimeout(go, ms)
}

function readRoute(): Route {
  const route = routeFromHash(window.location.hash)
  // Old hashes (#/dashboard, #/history, #/activation, #/next-batch) are replaced in the address bar.
  if (route.redirect) window.history.replaceState(null, '', route.redirect)
  return route
}

export function App() {
  const [signedIn, setSignedIn] = useState(false)
  const [checkingSession, setCheckingSession] = useState(true)
  const [sessionCheckError, setSessionCheckError] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)
  const [route, setRoute] = useState<Route>(readRoute)
  const heading = useRef<HTMLHeadingElement>(null)
  const view = route.view
  const screen = screenOf(route)
  const loop = useJourneyLoader(signedIn, window.location.hash)

  useEffect(
    () =>
      onUnauthorized(() => {
        setSignedIn(false)
        setNotice('Signed out: the passcode was not accepted. Enter it again.')
      }),
    [],
  )

  useEffect(() => {
    let cancelled = false
    const restore = async () => {
      try {
        const authenticated = await restoreSession()
        if (!cancelled) setSignedIn(authenticated)
      } catch (error) {
        if (error instanceof Error && 'status' in error && ((error as { status: number }).status === 0 || (error as { status: number }).status >= 500)) {
          if (!cancelled) setSessionCheckError(true)
        }
      } finally {
        if (!cancelled) setCheckingSession(false)
      }
    }
    void restore()
    return () => { cancelled = true }
  }, [])

  const shownScreen = useRef(screen)
  useEffect(() => {
    shownScreen.current = screen
  })

  useEffect(() => {
    const onHash = () => {
      const next = readRoute()
      setRoute(next)
      // A chip or tab within the same screen keeps focus where it is; guide anchors move focus themselves.
      if (screenOf(next) === shownScreen.current && !next.section) return
      if (!next.anchor)
        requestAnimationFrame(() => {
          heading.current?.focus({ preventScroll: Boolean(next.section) })
          scrollToSection(next.section)
        })
    }
    window.addEventListener('hashchange', onHash)
    return () => window.removeEventListener('hashchange', onHash)
  }, [])

  useEffect(() => {
    if (signedIn && route.section) requestAnimationFrame(() => scrollToSection(route.section))
    // Only on sign-in: later section changes scroll from the hashchange handler.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signedIn])

  /** Go to a route path such as `studio/make` or `settings#activation` (without `#/`). */
  const navigate = useCallback((path: string) => {
    if (window.location.hash !== `#/${path}`) window.location.hash = `/${path}`
    else requestAnimationFrame(() => heading.current?.focus())
  }, [])

  const signOut = useCallback(async () => {
    await api.logoutSession()
    clearPasscode()
    setSignedIn(false)
    setNotice('Signed out.')
  }, [])

  if (!signedIn) {
    if (checkingSession) return <main id="main" className="main"><p role="status">Checking sign-in…</p></main>
    if (sessionCheckError) return <main id="main" className="main"><h1>Scalar publishing</h1><p className="notice notice-warn" role="alert">Could not check your sign-in. Check the connection and retry before signing in.</p><button className="btn btn-primary" onClick={() => { setSessionCheckError(false); setCheckingSession(true); void api.session().then((result) => setSignedIn(result.authenticated)).catch(() => setSessionCheckError(true)).finally(() => setCheckingSession(false)) }}>Retry</button></main>
    return (
      <PasscodeView
        notice={notice}
        onSignedIn={() => {
          setNotice(null)
          setSignedIn(true)
        }}
      />
    )
  }

  const episode = view === 'library' ? route.episode : undefined
  const running = loop.update?.runningCommit ?? null
  return (
    <JourneyContext.Provider value={loop}>
      <div className="app-shell">
        <a
          className="skip-link"
          href="#main"
          onClick={(e) => {
            e.preventDefault()
            heading.current?.focus()
          }}
        >
          Skip to content
        </a>
        <header className="app-header">
          <p className="brand">Scalar publishing</p>
          <a className="help-link" href={guideHash(helpAnchor(route, screen))} aria-label="Help: open the guide for this screen" title="Guide">
            ?
          </a>
        </header>
        <AppNav current={view === 'guide' ? null : view} version={running ? shortHash(running, 7) : null} onNavigate={navigate} />
        <main id="main" className="main">
          <div className="view-head">
            <h1 ref={heading} tabIndex={-1} className="view-title">
              {SCREEN_TITLES[screen]}
            </h1>
            {screen === 'guide' ? null : <StepLine step={screenStep(screen, loop.journey)} />}
          </div>
          {view === 'home' ? <DashboardView onNavigate={navigate} /> : null}
          {view === 'activity' ? (
            <ActivityView tab={route.tab ?? 'all'} onTab={(tab) => navigate(tab === 'all' ? 'activity' : `activity?tab=${tab}`)} />
          ) : null}
          {view === 'library' && episode ? (
            <EpisodeDetailView key={`${episode.episodeId}@${episode.revision}`} episodeId={episode.episodeId} revision={episode.revision} />
          ) : null}
          {view === 'studio' && route.make ? <MakeBatchView key={route.project ?? ''} project={route.project} /> : null}
          {view === 'studio' && route.export ? (
            <Suspense fallback={<Loading />}>
              <ExportView />
            </Suspense>
          ) : null}
          {view === 'studio' && route.newFormat ? <NewFormatView /> : null}
          {view === 'studio' && route.jobs ? <StoryJobsView /> : null}
          {view === 'studio' && route.job ? <StoryJobView key={route.job} id={route.job} /> : null}
          {view === 'studio' && route.renders ? <StoryRendersView /> : null}
          {view === 'studio' && route.storySettings ? <StorySettingsView /> : null}
          {screen === 'studio' ? <StudioView /> : null}
          {view === 'library' && !episode ? <LibraryView /> : null}
          {view === 'schedule' ? <ScheduleView queue={Boolean(route.queue)} /> : null}
          {view === 'guide' ? <GuideView anchor={route.anchor} /> : null}
          {view === 'settings' ? <SettingsView onSignOut={signOut} /> : null}
        </main>
      </div>
    </JourneyContext.Provider>
  )
}

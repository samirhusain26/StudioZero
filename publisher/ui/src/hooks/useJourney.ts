import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { api } from '../api/client'
import type { DashboardResponse, UpdateInfo } from '../api/types'
import { journey, type Journey } from '../lib/journey'
import { MAKE_EVENT, pruneMake, readMake } from '../lib/makeChecklist'

/** Reload the shell's dashboard copy on navigation when it is older than this. */
const STALE_MS = 15_000

export interface JourneyState {
  journey: Journey | null
  dashboard: DashboardResponse | null
  update: UpdateInfo | null
  /** Reload now (after a mutation that changes the loop, e.g. an approval). */
  reload: () => void
  /** A screen that polls the dashboard itself (Home) hands each fresh copy here, so the step line and Home agree. */
  accept: (dashboard: DashboardResponse) => void
}

const EMPTY: JourneyState = { journey: null, dashboard: null, update: null, reload: () => {}, accept: () => {} }

export const JourneyContext = createContext<JourneyState>(EMPTY)

export function useJourney(): JourneyState {
  return useContext(JourneyContext)
}

/**
 * The shell's view of the loop: the dashboard payload and the last update check, loaded once after sign-in and
 * again on navigation when stale, plus the browser-local Make checklist. Failures keep the last good copy
 * (screens show their own errors).
 */
export function useJourneyLoader(enabled: boolean, navKey: string): JourneyState {
  const [dashboard, setDashboard] = useState<DashboardResponse | null>(null)
  const [update, setUpdate] = useState<UpdateInfo | null>(null)
  const [makeTick, setMakeTick] = useState(0)
  const loadedAt = useRef(0)
  const inFlight = useRef(false)

  const load = useCallback(() => {
    if (inFlight.current) return
    inFlight.current = true
    loadedAt.current = Date.now()
    Promise.allSettled([api.dashboard(), api.updateStatus()])
      .then(([d, u]) => {
        if (d.status === 'fulfilled') setDashboard(d.value)
        if (u.status === 'fulfilled') setUpdate(u.value)
      })
      .finally(() => {
        inFlight.current = false
      })
  }, [])

  useEffect(() => {
    if (enabled && Date.now() - loadedAt.current >= STALE_MS) load()
  }, [enabled, navKey, load])

  useEffect(() => {
    const bump = () => setMakeTick((n) => n + 1)
    window.addEventListener(MAKE_EVENT, bump)
    window.addEventListener('storage', bump)
    return () => {
      window.removeEventListener(MAKE_EVENT, bump)
      window.removeEventListener('storage', bump)
    }
  }, [])

  const nextBatchId = dashboard?.standing?.nextBatchId ?? null
  useEffect(() => {
    if (nextBatchId) pruneMake(nextBatchId)
  }, [nextBatchId])

  const j = useMemo(() => {
    void makeTick
    return journey({ dashboard, update, make: nextBatchId ? readMake(nextBatchId) : null, now: new Date() })
  }, [dashboard, update, nextBatchId, makeTick])

  const accept = useCallback((fresh: DashboardResponse) => {
    loadedAt.current = Date.now()
    setDashboard(fresh)
  }, [])

  return useMemo(() => ({ journey: j, dashboard, update, reload: load, accept }), [j, dashboard, update, load, accept])
}

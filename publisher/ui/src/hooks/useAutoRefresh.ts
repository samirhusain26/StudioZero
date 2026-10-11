import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiRequestError, waitText } from '../api/client'

export const AUTO_REFRESH_MS = 30_000

export interface AutoRefreshState<T> {
  data: T | null
  error: unknown
  loading: boolean
  /** When the last successful load finished. */
  updatedAt: Date | null
  /** Auto-refresh switched on by the owner (default on). */
  auto: boolean
  setAuto: (on: boolean) => void
  /** Set when polling stopped itself (401 / 429); a manual reload clears it. */
  stopped: string | null
  reload: () => void
  setData: (data: T) => void
}

/** Why polling stops on its own: the passcode was refused, or the Pi asked us to back off. */
export function stopReason(error: unknown): string | null {
  if (!(error instanceof ApiRequestError)) return null
  if (error.status === 401) return 'Auto-refresh stopped: the passcode was not accepted.'
  if (error.status === 429) {
    const wait = error.retryAfterSeconds ? ` Wait ${waitText(error.retryAfterSeconds)}, then refresh.` : ''
    return `Auto-refresh stopped: too many attempts.${wait}`
  }
  return null
}

function visible(): boolean {
  return typeof document === 'undefined' || document.visibilityState !== 'hidden'
}

/**
 * Loads on mount (and when `key` changes), then every `intervalMs` while the tab is visible and
 * auto-refresh is on. Requests never overlap: a tick is skipped while one is in flight, and the next
 * timer starts only after a load settles. Hidden tabs do not poll; on becoming visible a stale view
 * refreshes at once. 401/429 stop polling until the owner reloads manually.
 */
export function useAutoRefresh<T>(load: (signal: AbortSignal) => Promise<T>, key = '', intervalMs = AUTO_REFRESH_MS): AutoRefreshState<T> {
  const [data, setDataState] = useState<T | null>(null)
  const [error, setError] = useState<unknown>(null)
  const [loading, setLoading] = useState(true)
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null)
  const [auto, setAuto] = useState(true)
  const [stopped, setStopped] = useState<string | null>(null)
  const loadRef = useRef(load)
  const inFlight = useRef<AbortController | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastAt = useRef(0)
  const live = useRef({ auto, stopped })
  useEffect(() => {
    loadRef.current = load
    live.current = { auto, stopped }
  })

  const runRef = useRef<() => Promise<void>>(() => Promise.resolve())

  const clearTimer = useCallback(() => {
    if (timer.current) clearTimeout(timer.current)
    timer.current = null
  }, [])

  const schedule = useCallback(
    (delay: number) => {
      clearTimer()
      if (!live.current.auto || live.current.stopped || !visible()) return
      timer.current = setTimeout(() => void runRef.current(), Math.max(0, delay))
    },
    [clearTimer],
  )

  const run = useCallback(async () => {
    if (inFlight.current) return
    const controller = new AbortController()
    inFlight.current = controller
    setLoading(true)
    try {
      const next = await loadRef.current(controller.signal)
      if (controller.signal.aborted) return
      setDataState(next)
      setError(null)
      lastAt.current = Date.now()
      setUpdatedAt(new Date(lastAt.current))
    } catch (e) {
      if (controller.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) return
      setError(e)
      const reason = stopReason(e)
      if (reason) {
        live.current = { ...live.current, stopped: reason }
        setStopped(reason)
      }
    } finally {
      if (inFlight.current === controller) inFlight.current = null
      if (!controller.signal.aborted) {
        setLoading(false)
        schedule(intervalMs)
      }
    }
  }, [intervalMs, schedule])

  useEffect(() => {
    runRef.current = run
  }, [run])

  // Initial load and reload on key change.
  useEffect(() => {
    void run()
    return () => {
      inFlight.current?.abort()
      inFlight.current = null
      clearTimer()
    }
  }, [key, run, clearTimer])

  // Auto toggle and visibility.
  useEffect(() => {
    if (!auto || stopped) {
      clearTimer()
      return
    }
    const onVisibility = () => {
      if (!visible()) {
        clearTimer()
        return
      }
      const age = Date.now() - lastAt.current
      if (age >= intervalMs) void run()
      else schedule(intervalMs - age)
    }
    onVisibility()
    document.addEventListener('visibilitychange', onVisibility)
    return () => {
      document.removeEventListener('visibilitychange', onVisibility)
      clearTimer()
    }
  }, [auto, stopped, intervalMs, run, schedule, clearTimer])

  const reload = useCallback(() => {
    live.current = { ...live.current, stopped: null }
    setStopped(null)
    void run()
  }, [run])

  const setData = useCallback((value: T) => {
    setDataState(value)
    setError(null)
  }, [])

  return { data, error, loading, updatedAt, auto, setAuto, stopped, reload, setData }
}

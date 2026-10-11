import { useCallback, useEffect, useRef, useState } from 'react'

export interface ApiState<T> {
  data: T | null
  error: unknown
  loading: boolean
  reload: () => void
  /** Replace data locally (e.g. after a mutation returned fresh data). */
  setData: (data: T) => void
}

interface Loaded<T> {
  token: string
  data: T | null
  error: unknown
}

/** Loads on mount and whenever `key` changes; keeps previous data while reloading. */
export function useApi<T>(load: () => Promise<T>, key = ''): ApiState<T> {
  const [nonce, setNonce] = useState(0)
  const [loaded, setLoaded] = useState<Loaded<T>>({ token: '', data: null, error: null })
  const loadRef = useRef(load)
  useEffect(() => {
    loadRef.current = load
  })
  const token = `${key}\u0000${nonce}`
  useEffect(() => {
    let cancelled = false
    loadRef.current().then(
      (data) => {
        if (!cancelled) setLoaded({ token, data, error: null })
      },
      (error: unknown) => {
        if (!cancelled) setLoaded((prev) => ({ token, data: prev.data, error }))
      },
    )
    return () => {
      cancelled = true
    }
  }, [token])
  const reload = useCallback(() => setNonce((n) => n + 1), [])
  const setData = useCallback((data: T) => setLoaded((prev) => ({ ...prev, data, error: null })), [])
  return { data: loaded.data, error: loaded.error, loading: loaded.token !== token, reload, setData }
}

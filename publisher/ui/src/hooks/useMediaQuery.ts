import { useEffect, useState } from 'react'

/** Desktop layout breakpoint shared with styles.css. */
export const DESKTOP = '(min-width: 1024px)'

function matches(query: string): boolean {
  return typeof window !== 'undefined' && typeof window.matchMedia === 'function' && window.matchMedia(query).matches
}

/** True while the media query matches (false where matchMedia is missing, e.g. tests). */
export function useMediaQuery(query: string): boolean {
  const [on, setOn] = useState(() => matches(query))
  useEffect(() => {
    if (typeof window.matchMedia !== 'function') return
    const list = window.matchMedia(query)
    const change = () => setOn(list.matches)
    change()
    list.addEventListener('change', change)
    return () => list.removeEventListener('change', change)
  }, [query])
  return on
}
